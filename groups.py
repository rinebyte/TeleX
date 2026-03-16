import asyncio
import logging

from pyrogram import enums
from pyrogram.errors import RPCError
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress
from rich.prompt import Prompt, Confirm

import db as _default_db
from ratelimit import rate_limiter as _default_rate_limiter

log = logging.getLogger("telex.groups")


async def check_premium_status(app, console, db=None, rate_limiter=None):
    """Check if the account has Telegram Premium."""
    console.print("[yellow]Checking premium status...[/]")

    try:
        me = await app.get_me()
    except RPCError as e:
        console.print(f"[red]Failed to fetch account info: {e}[/]")
        return

    if me.is_premium:
        status = "[bold green]Active[/bold green] — You have Telegram Premium"
    else:
        status = "[bold red]Inactive[/bold red] — No Telegram Premium"

    console.print(Panel(
        f"Account: [cyan]{me.first_name or ''} {me.last_name or ''}[/cyan]\n"
        f"Username: [cyan]@{me.username or '—'}[/cyan]\n"
        f"Premium: {status}",
        title="[bold cyan]Premium Status[/]",
        border_style="cyan",
    ))
    log.info("Premium check: %s (premium=%s)", me.username, me.is_premium)


async def check_spam_status(app, console, db=None, rate_limiter=None):
    """Check account spam status via @SpamBot."""
    console.print("[yellow]Checking spam status...[/]")

    try:
        await app.send_message("SpamBot", "/start")
    except RPCError as e:
        console.print(f"[red]Failed to contact @SpamBot: {e}[/]")
        return

    # Poll for response (SpamBot replies within 1-2s, poll up to 10s)
    for _ in range(5):
        await asyncio.sleep(2)
        async for msg in app.get_chat_history("SpamBot", limit=1):
            if not msg.outgoing:
                console.print(Panel(
                    msg.text or "[no response]",
                    title="[bold cyan]@SpamBot[/]",
                    border_style="cyan",
                ))
                log.info("Spam check result: %s", (msg.text or "")[:80])
                return

    console.print("[red]@SpamBot didn't respond in time.[/]")


async def fetch_all_groups(app, console, db=None, rate_limiter=None):
    """Fetch and display all joined groups/channels from Telegram."""
    console.print("[yellow]Fetching all groups...[/]")

    groups = []
    async for dialog in app.get_dialogs():
        chat = dialog.chat
        if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL):
            groups.append(chat)

    if not groups:
        console.print("[red]No groups found.[/]")
        return

    table = Table(title=f"All Joined Groups ({len(groups)})")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("Username", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Members", justify="right")

    for i, chat in enumerate(groups, 1):
        table.add_row(
            str(i),
            chat.title or "—",
            f"@{chat.username}" if chat.username else "—",
            chat.type.name,
            str(chat.members_count or 0),
        )

    console.print(table)
    log.info("Fetched %d groups total", len(groups))


async def find_and_leave_restricted(app, console, db=None, rate_limiter=None):
    db = db or _default_db
    rate_limiter = rate_limiter or _default_rate_limiter
    """Find groups where user can't send messages and offer to leave."""
    console.print("[yellow]Fetching groups...[/]")

    groups = []
    async for dialog in app.get_dialogs():
        chat = dialog.chat
        if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL):
            groups.append(chat)

    if not groups:
        console.print("[red]No groups found.[/]")
        return

    console.print(f"[yellow]Checking send permissions for {len(groups)} groups...[/]")

    restricted = []
    with Progress(console=console) as progress:
        task = progress.add_task("[yellow]Checking...", total=len(groups))
        for chat in groups:
            try:
                if not await _check_can_send(app, chat, rate_limiter=rate_limiter):
                    restricted.append(chat)
            except Exception as e:
                log.debug("Error checking %s: %s", chat.title, e)
            progress.advance(task)

    if not restricted:
        console.print("[green]All groups allow sending messages.[/]")
        return

    table = Table(title=f"Restricted Groups ({len(restricted)})")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("Username", style="green")
    table.add_column("Type", style="yellow")

    for i, chat in enumerate(restricted, 1):
        table.add_row(
            str(i),
            chat.title or "—",
            f"@{chat.username}" if chat.username else "—",
            chat.type.name,
        )

    console.print(table)

    selection = Prompt.ask(
        "[cyan]Select groups to leave (comma-separated numbers or 'all')[/]"
    )

    if selection.strip().lower() == "all":
        selected = restricted
    else:
        try:
            indices = [int(x.strip()) - 1 for x in selection.split(",")]
            selected = [restricted[i] for i in indices if 0 <= i < len(restricted)]
        except (ValueError, IndexError):
            console.print("[red]Invalid selection.[/]")
            return

    if not selected:
        console.print("[red]No groups selected.[/]")
        return

    if Confirm.ask(f"[yellow]Leave {len(selected)} group(s)?[/]"):
        await _leave_groups(app, selected, console, db=db, rate_limiter=rate_limiter)


async def _check_can_send(app, chat, rate_limiter=None) -> bool:
    """Check if current user can send messages in a chat."""
    rate_limiter = rate_limiter or _default_rate_limiter
    try:
        member = await rate_limiter.call(
            lambda: app.get_chat_member(chat.id, "me")
        )
    except RPCError:
        return True  # Can't determine, assume accessible

    # Owner/Admin can always send
    if member.status in (enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR):
        return True

    # Channels: only admins can post
    if chat.type == enums.ChatType.CHANNEL:
        return False

    # Restricted: check user-specific permissions
    if member.status == enums.ChatMemberStatus.RESTRICTED:
        if member.permissions:
            return member.permissions.can_send_messages is not False
        return False

    # Regular member: check default group permissions
    if chat.permissions:
        return chat.permissions.can_send_messages is not False

    return True


async def _leave_groups(app, groups, console, db=None, rate_limiter=None):
    """Leave a list of groups with rate limiting."""
    db = db or _default_db
    rate_limiter = rate_limiter or _default_rate_limiter
    left = 0

    with Progress(console=console) as progress:
        task = progress.add_task("[red]Leaving...", total=len(groups))
        for chat in groups:
            try:
                await rate_limiter.call(lambda c=chat: app.leave_chat(c.id), console)
                db.remove_group(chat.id)
                console.print(f"  [green]✓[/] Left: {chat.title}")
                left += 1
            except RPCError as e:
                console.print(f"  [red]✗ Failed: {chat.title} — {e}[/]")
            progress.advance(task)

    log.info("Left %d/%d restricted groups", left, len(groups))
    console.print(f"\n[green]Left {left}/{len(groups)} groups.[/]")
