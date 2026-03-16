import asyncio
import contextlib
import logging
import re

from pyrogram.errors import ChatWriteForbidden, FloodWait, RPCError, SlowmodeWait, UserBannedInChannel
from rich.console import Console as RichConsole
from rich.table import Table
from rich.progress import Progress
from rich.prompt import Prompt, Confirm

import db as _default_db
from config import BLAST_DELAY, BLAST_BATCH_SIZE
from models import SavedGroup
from ratelimit import rate_limiter as _default_rate_limiter

log = logging.getLogger("telex.blast")


def _chat_target(g) -> str | int:
    """Prefer @username (always resolvable) over numeric ID (needs cached access hash)."""
    return f"@{g['username']}" if g.get("username") else g["id"]


def _parse_message_link(link: str) -> tuple[str | int, int] | None:
    """Parse a t.me message link into (chat, message_id).

    Supports:
      https://t.me/username/123
      https://t.me/username/topic/123       (topic thread)
      https://t.me/c/1234567890/123         (private supergroup)
      https://t.me/c/1234567890/topic/123   (private topic thread)
    """
    stripped = link.strip()

    # Private: t.me/c/{id}/{msg} or t.me/c/{id}/{topic}/{msg}
    m = re.match(r"(?:https?://)?t\.me/c/(\d+)/(?:\d+/)*(\d+)", stripped)
    if m:
        return int(f"-100{m.group(1)}"), int(m.group(2))

    # Public: t.me/{username}/{msg} or t.me/{username}/{topic}/{msg}
    m = re.match(r"(?:https?://)?t\.me/([a-zA-Z_]\w+)/(?:\d+/)*(\d+)", stripped)
    if m:
        return m.group(1), int(m.group(2))

    return None


async def blast_message(app, targets: list[SavedGroup], text: str, console, db=None, rate_limiter=None):
    db = db or _default_db
    rate_limiter = rate_limiter or _default_rate_limiter
    sent = 0
    lock = asyncio.Lock()
    banned = asyncio.Event()
    _has_progress = isinstance(console, RichConsole)

    async def _send_one(g, progress=None, task=None):
        nonlocal sent
        if banned.is_set():
            if progress:
                progress.advance(task)
            return
        try:
            await rate_limiter.call(lambda g=g: app.send_message(_chat_target(g), text), console)
            console.print(f"  [green]✓[/] Sent to: {g['title']}")
            async with lock:
                sent += 1
        except UserBannedInChannel:
            banned.set()
            console.print("[red]⛔ Account restricted — aborting blast. Check @SpamBot.[/]")
        except ChatWriteForbidden:
            db.remove_group(g["id"])
            console.print(f"  [red]✗ No permission: {g['title']} [dim](removed from DB)[/]")
        except SlowmodeWait as e:
            console.print(f"  [yellow]⏭ Slow mode ({e.value}s): {g['title']} — skipped[/]")
        except (FloodWait, RPCError) as e:
            console.print(f"  [red]✗ Failed: {g['title']} — {e}[/]")
        if progress:
            progress.advance(task)

    progress_cm = Progress(console=console) if _has_progress else contextlib.nullcontext()
    with progress_cm as progress:
        task = progress.add_task("[green]Blasting...", total=len(targets)) if progress else None
        for i in range(0, len(targets), BLAST_BATCH_SIZE):
            batch = targets[i:i + BLAST_BATCH_SIZE]
            await asyncio.gather(*[_send_one(g, progress, task) for g in batch])
            if not _has_progress:
                console.print(f"[dim]Progress: {min(i + BLAST_BATCH_SIZE, len(targets))}/{len(targets)}[/]")
            if i + BLAST_BATCH_SIZE < len(targets):
                await asyncio.sleep(rate_limiter.get_delay(BLAST_DELAY))

    log.info("Blast complete: %d/%d groups", sent, len(targets))
    console.print(f"\n[green]Sent to {sent}/{len(targets)} groups.[/]")
    if banned.is_set():
        console.print("[red]⚠ Blast aborted early — account restricted. Check @SpamBot for details.[/]")


async def blast_copy(app, targets: list[SavedGroup], from_chat, message_id: int, console, db=None, rate_limiter=None):
    """Copy a message from one chat to multiple targets (preserves formatting, media, premium emoji)."""
    db = db or _default_db
    rate_limiter = rate_limiter or _default_rate_limiter
    sent = 0
    lock = asyncio.Lock()
    banned = asyncio.Event()
    _has_progress = isinstance(console, RichConsole)

    async def _copy_one(g, progress=None, task=None):
        nonlocal sent
        if banned.is_set():
            if progress:
                progress.advance(task)
            return
        try:
            await rate_limiter.call(
                lambda g=g: app.copy_message(_chat_target(g), from_chat, message_id),
                console,
            )
            console.print(f"  [green]✓[/] Sent to: {g['title']}")
            async with lock:
                sent += 1
        except UserBannedInChannel:
            banned.set()
            console.print("[red]⛔ Account restricted — aborting blast. Check @SpamBot.[/]")
        except ChatWriteForbidden:
            db.remove_group(g["id"])
            console.print(f"  [red]✗ No permission: {g['title']} [dim](removed from DB)[/]")
        except SlowmodeWait as e:
            console.print(f"  [yellow]⏭ Slow mode ({e.value}s): {g['title']} — skipped[/]")
        except (FloodWait, RPCError) as e:
            console.print(f"  [red]✗ Failed: {g['title']} — {e}[/]")
        if progress:
            progress.advance(task)

    progress_cm = Progress(console=console) if _has_progress else contextlib.nullcontext()
    with progress_cm as progress:
        task = progress.add_task("[green]Blasting...", total=len(targets)) if progress else None
        for i in range(0, len(targets), BLAST_BATCH_SIZE):
            batch = targets[i:i + BLAST_BATCH_SIZE]
            await asyncio.gather(*[_copy_one(g, progress, task) for g in batch])
            if not _has_progress:
                console.print(f"[dim]Progress: {min(i + BLAST_BATCH_SIZE, len(targets))}/{len(targets)}[/]")
            if i + BLAST_BATCH_SIZE < len(targets):
                await asyncio.sleep(rate_limiter.get_delay(BLAST_DELAY))

    log.info("Blast copy complete: %d/%d groups", sent, len(targets))
    console.print(f"\n[green]Sent to {sent}/{len(targets)} groups.[/]")
    if banned.is_set():
        console.print("[red]⚠ Blast aborted early — account restricted. Check @SpamBot for details.[/]")


async def blast_menu(app, console, db=None, rate_limiter=None):
    db = db or _default_db
    rate_limiter = rate_limiter or _default_rate_limiter
    groups = db.get_all_groups()
    if not groups:
        console.print("[red]No joined groups in database. Search & join groups first.[/]")
        return

    table = Table(title="Joined Groups")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="cyan")
    table.add_column("Username", style="green")
    table.add_column("ID", style="dim")
    for i, g in enumerate(groups, 1):
        table.add_row(str(i), g["title"], f"@{g['username'] or '—'}", str(g["id"]))
    console.print(table)

    selection = Prompt.ask(
        "[cyan]Select target groups (comma-separated numbers or 'all')[/]"
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

    # Dedup by username — migrated groups share the same username with different IDs
    seen = set()
    deduped = []
    for g in selected:
        key = g.get("username") or g["id"]
        if key not in seen:
            seen.add(key)
            deduped.append(g)
    if len(deduped) < len(selected):
        console.print(f"[yellow]Removed {len(selected) - len(deduped)} duplicate(s).[/]")
    selected = deduped

    text = Prompt.ask("[cyan]Enter message or paste t.me message link[/]")
    if not text.strip():
        console.print("[red]Input cannot be empty.[/]")
        return

    parsed = _parse_message_link(text.strip())

    if parsed:
        from_chat, msg_id = parsed

        # Private links (numeric ID) need peer resolution from dialogs
        if isinstance(from_chat, int):
            try:
                await app.resolve_peer(from_chat)
            except (KeyError, RPCError):
                console.print("[yellow]Resolving private chat...[/]")
                found = False
                async for dialog in app.get_dialogs():
                    if dialog.chat.id == from_chat:
                        found = True
                        break
                if not found:
                    console.print("[red]Chat not found. Make sure you're a member.[/]")
                    return

        try:
            msg = await app.get_messages(from_chat, msg_id)
            if msg.empty:
                console.print("[red]Message not found or deleted.[/]")
                return
        except RPCError as e:
            console.print(f"[red]Failed to fetch message: {e}[/]")
            return

        preview = msg.text or msg.caption or ""
        if msg.media:
            media_type = msg.media.value.replace("_", " ")
            preview = f"[{media_type}] {preview}" if preview else f"[{media_type}]"

        console.print(f"\n[yellow]Targets: {len(selected)} group(s)[/]")
        console.print(f"[yellow]Message:[/] {preview[:200]}")

        if Confirm.ask("[yellow]Send?[/]"):
            await blast_copy(app, selected, from_chat, msg_id, console, db=db, rate_limiter=rate_limiter)
    else:
        console.print(f"\n[yellow]Targets: {len(selected)} group(s)[/]")
        console.print(f"[yellow]Message:[/] {text}")

        if Confirm.ask("[yellow]Send?[/]"):
            await blast_message(app, selected, text, console, db=db, rate_limiter=rate_limiter)
