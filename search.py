import asyncio
import contextlib
import logging

from pyrogram import enums, raw
from pyrogram.errors import FloodWait, RPCError
from rich.console import Console as RichConsole
from rich.table import Table
from rich.progress import Progress
from rich.prompt import Prompt, Confirm

import db as _default_db
from config import JOIN_DELAY
from models import GroupData
from ratelimit import rate_limiter as _default_rate_limiter

log = logging.getLogger("telex.search")


async def search_groups(app, keyword: str, limit: int = 100) -> list[GroupData]:
    results = {}  # chat_id -> dict, for dedup
    kw_lower = keyword.lower()

    # Method 1: contacts.Search — searches groups/channels by name directly
    try:
        found = await app.invoke(
            raw.functions.contacts.Search(q=keyword, limit=100)
        )
        for chat in found.chats:
            if not hasattr(chat, 'username') or not chat.username:
                continue
            # Accept supergroups and regular groups, skip broadcast channels
            if isinstance(chat, raw.types.Channel) and getattr(chat, 'broadcast', False):
                continue
            if isinstance(chat, (raw.types.Channel, raw.types.Chat)):
                results[chat.id] = {
                    "id": chat.id, "title": chat.title or "",
                    "username": chat.username,
                    "members": getattr(chat, 'participants_count', 0) or 0,
                }
    except RPCError:
        pass

    # Method 2: search_global — supplement with message-based search
    # Only add groups whose title contains the keyword to avoid irrelevant results
    try:
        async for message in app.search_global(keyword, limit=limit * 10):
            chat = message.chat
            if chat is None or chat.id in results:
                continue
            if chat.type not in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
                continue
            if not chat.username:
                continue
            # Filter: title must contain at least one keyword word
            title_lower = (chat.title or "").lower()
            if not any(w in title_lower for w in kw_lower.split()):
                continue
            results[chat.id] = {
                "id": chat.id, "title": chat.title or "",
                "username": chat.username,
                "members": chat.members_count or 0,
            }
            if len(results) >= limit:
                break
    except RPCError:
        pass

    # Sort by member count descending
    sorted_results = sorted(results.values(), key=lambda g: g["members"], reverse=True)
    return sorted_results[:limit]


async def join_groups(app, groups: list[GroupData], console, db=None, rate_limiter=None):
    db = db or _default_db
    rate_limiter = rate_limiter or _default_rate_limiter
    joined = 0
    lock = asyncio.Lock()
    _has_progress = isinstance(console, RichConsole)

    async def _join_one(g, progress=None, task=None):
        nonlocal joined
        try:
            await rate_limiter.call(lambda g=g: app.join_chat(g["username"]), console)
            db.save_group(g["id"], g["title"], g["username"])
            console.print(f"  [green]✓[/] Joined: {g['title']}")
            async with lock:
                joined += 1
        except (FloodWait, RPCError) as e:
            console.print(f"  [red]✗ Failed: {g['title']} — {e}[/]")
        if progress:
            progress.advance(task)

    progress_cm = Progress(console=console) if _has_progress else contextlib.nullcontext()
    with progress_cm as progress:
        task = progress.add_task("[green]Joining groups...", total=len(groups)) if progress else None
        i = 0
        while i < len(groups):
            bs = rate_limiter.batch_size
            batch = groups[i:i + bs]
            await asyncio.gather(*[_join_one(g, progress, task) for g in batch])
            i += bs
            if not _has_progress:
                console.print(f"[dim]Progress: {min(i, len(groups))}/{len(groups)}[/]")
            if i < len(groups):
                await asyncio.sleep(rate_limiter.get_delay(JOIN_DELAY))

    console.print(f"\n[green]Joined {joined}/{len(groups)} groups.[/]")


async def search_and_join_menu(app, console, db=None, rate_limiter=None):
    db = db or _default_db
    rate_limiter = rate_limiter or _default_rate_limiter
    keyword = Prompt.ask("[cyan]Enter search keyword[/]")
    if not keyword.strip():
        console.print("[red]Keyword cannot be empty.[/]")
        return

    console.print(f"[yellow]Searching for '{keyword}'...[/]")
    groups = await search_groups(app, keyword)
    log.info("Search '%s' returned %d results", keyword, len(groups))

    if not groups:
        console.print("[red]No groups found.[/]")
        return

    table = Table(title=f"Search Results: '{keyword}'")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("Username", style="green")
    table.add_column("Members", justify="right")
    for i, g in enumerate(groups, 1):
        table.add_row(str(i), g["title"], f"@{g['username']}", str(g["members"]))
    console.print(table)

    selection = Prompt.ask(
        "[cyan]Select groups to join (comma-separated numbers or 'all')[/]"
    )

    if selection.strip().lower() == "all":
        selected = groups
    else:
        try:
            indices = [int(x.strip()) - 1 for x in selection.split(",")]
            selected = [groups[i] for i in indices if 0 <= i < len(groups)]
        except (ValueError, IndexError):
            console.print("[red]Invalid selection.[/]")
            return

    if not selected:
        console.print("[red]No groups selected.[/]")
        return

    if Confirm.ask(f"[yellow]Join {len(selected)} group(s)?[/]"):
        await join_groups(app, selected, console, db=db, rate_limiter=rate_limiter)
