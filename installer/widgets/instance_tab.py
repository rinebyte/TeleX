"""Per-instance tab: RichLog output + Input for menu interaction."""

import asyncio
import logging
import sys
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog, Static, TabbedContent, TabPane

# Ensure TeleX project root is importable
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from installer.instance_manager import InstanceConfig
from installer.output_adapter import OutputAdapter

log = logging.getLogger("telex.instance")


class InstanceTab(Vertical):
    """A tab that runs a single TeleX instance."""

    DEFAULT_CSS = """
    InstanceTab {
        height: 1fr;
    }
    InstanceTab RichLog {
        height: 1fr;
        border: solid $accent;
        scrollbar-size: 1 1;
    }
    InstanceTab #status-bar {
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    InstanceTab Input {
        dock: bottom;
    }
    """

    def __init__(self, config: InstanceConfig, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.adapter: OutputAdapter | None = None
        self._status = "disconnected"
        self._client = None

    def compose(self) -> ComposeResult:
        yield Static(f"[dim]{self.config.name}[/] — disconnected", id="status-bar")
        yield RichLog(highlight=True, markup=True, wrap=True, id="output")
        yield Input(placeholder="Enter command...", id="input")

    def on_mount(self) -> None:
        rich_log = self.query_one("#output", RichLog)
        self.adapter = OutputAdapter(rich_log=rich_log, on_ask=self._on_ask_callback)
        self._start_instance()

    def _on_ask_callback(self, prompt: str) -> None:
        """Called when adapter.ask() fires — focus input and set placeholder."""
        try:
            inp = self.query_one("#input", Input)
            inp.placeholder = prompt
            inp.focus()
        except Exception:
            pass

    def on_unmount(self) -> None:
        """Cancel workers and stop the Pyrogram client on tab removal / app quit."""
        # Cancel all running workers for this widget
        for worker in self.workers:
            worker.cancel()
        # Stop the client with a timeout
        if self._client is not None:
            client = self._client
            self._client = None
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._stop_client_with_timeout(client, timeout=5.0))
            except RuntimeError:
                pass

    @staticmethod
    async def _stop_client_with_timeout(client, timeout: float = 5.0):
        """Stop a Pyrogram client with a timeout so it doesn't hang."""
        try:
            await asyncio.wait_for(client.stop(), timeout=timeout)
        except (asyncio.TimeoutError, Exception):
            try:
                await client.disconnect()
            except Exception:
                pass

    def _update_status(self, status: str, style: str = ""):
        self._status = status
        label = f"[dim]{self.config.name}[/] — "
        if style:
            label += f"[{style}]{status}[/{style}]"
        else:
            label += status
        try:
            self.query_one("#status-bar", Static).update(label)
        except Exception:
            pass
        # Update tab pane label with status dot
        self._update_tab_label(status)

    def _update_tab_label(self, status: str) -> None:
        """Update the parent TabPane label with a colored status dot."""
        dot_map = {
            "connected": "[green]●[/green]",
            "connecting": "[yellow]●[/yellow]",
            "error": "[red]●[/red]",
            "disconnected": "[dim]○[/dim]",
        }
        dot = dot_map.get(status, "[dim]○[/dim]")
        # Walk up to find the TabPane, then the TabbedContent
        pane = None
        node = self.parent
        while node is not None:
            if isinstance(node, TabPane):
                pane = node
                break
            node = node.parent
        if pane is None:
            return
        try:
            tabs = self.screen.query_one(TabbedContent)
            tab = tabs.get_tab(pane.id)
            tab.label = f"{dot} {self.config.name}"
        except Exception:
            pass

    @work(thread=False)
    async def _start_instance(self) -> None:
        """Start the TeleX instance as an async worker."""
        from config import parse_proxy, SLEEP_THRESHOLD
        from db import Database
        from ratelimit import RateLimitState
        from pyrogram import Client, raw
        from pyrogram.errors import SessionPasswordNeeded, RPCError

        self.adapter.print(f"[cyan]Starting instance: {self.config.name}[/]")
        self._update_status("connecting", "yellow")

        work_dir = self.config.work_dir
        work_dir.mkdir(parents=True, exist_ok=True)

        database = Database(str(work_dir / "telex.db"))
        database.init_db()
        rate_limiter = RateLimitState()

        proxy = parse_proxy(self.config.proxy_url)
        proxy_kwargs = {"proxy": proxy} if proxy else {}

        client = Client(
            str(work_dir / "telex"),
            api_id=self.config.api_id,
            api_hash=self.config.api_hash,
            no_updates=True,
            sleep_threshold=SLEEP_THRESHOLD,
            **proxy_kwargs,
        )
        self._client = client

        try:
            # Use connect() instead of start() to avoid blocking input() on first login
            is_authorized = await client.connect()

            if not is_authorized:
                # First login — manual auth flow via OutputAdapter
                phone = self.config.phone
                self.adapter.print("[yellow]Sending verification code...[/]")
                try:
                    sent_code = await client.send_code(phone)
                except RPCError as e:
                    self.adapter.print(f"[red]Failed to send code: {e}[/]")
                    await client.disconnect()
                    self._client = None
                    self._update_status("error", "red")
                    return

                self.adapter.print("[green]Code sent! Check your Telegram app.[/]")

                signed_in = False
                while not signed_in:
                    code = await self.adapter.ask("Enter verification code")
                    code = code.strip().replace(" ", "").replace("-", "")
                    if not code:
                        self.adapter.print("[red]Code cannot be empty.[/]")
                        continue
                    try:
                        await client.sign_in(phone, sent_code.phone_code_hash, code)
                        signed_in = True
                    except SessionPasswordNeeded:
                        pwd = await self.adapter.ask("Enter 2FA password")
                        await client.check_password(pwd.strip())
                        signed_in = True
                    except RPCError as e:
                        self.adapter.print(f"[red]{e}. Try again.[/]")

            # Complete initialization (same as what Client.start() does after authorize)
            try:
                await client.invoke(raw.functions.updates.GetState())
            except Exception:
                pass
            await client.initialize()

        except asyncio.CancelledError:
            self._client = None
            try:
                await client.disconnect()
            except Exception:
                pass
            raise
        except Exception as e:
            self.adapter.print(f"[red]Failed to connect: {e}[/]")
            self._update_status("error", "red")
            self._client = None
            try:
                await client.disconnect()
            except Exception:
                pass
            return

        self._update_status("connected", "green")
        try:
            me = await client.get_me()
            self.adapter.print(
                f"[green]Logged in as {me.first_name or ''} (@{me.username or '—'})[/]"
            )
        except Exception:
            self.adapter.print("[green]Connected.[/]")

        if proxy:
            self.adapter.print(
                f"[cyan]Proxy:[/] {proxy['scheme']}://{proxy['hostname']}:{proxy['port']}"
            )

        # Run menu loop
        try:
            await self._menu_loop(client, database, rate_limiter)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.adapter.print(f"[red]Error: {e}[/]")
            log.exception("Menu loop error for %s", self.config.name)
        finally:
            self._client = None
            try:
                await client.stop()
            except Exception:
                pass
            self._update_status("disconnected", "dim")
            self.adapter.print("[dim]Type 'reconnect' to retry.[/]")

    async def _menu_loop(self, client, database, rate_limiter):
        """Interactive menu driven by the OutputAdapter."""
        import search
        import blast
        import groups
        from pyrogram import enums
        from pyrogram.errors import RPCError

        while True:
            self.adapter.print(
                "\n[bold cyan]Menu[/]\n"
                "[1] Search & Join Groups\n"
                "[2] Blast Message\n"
                "[3] Fetch All Groups\n"
                "[4] Find & Leave Restricted Groups\n"
                "[5] Check Spam Status\n"
                "[6] Check Premium Status\n"
                "[0] Disconnect"
            )

            choice = await self.adapter.ask("Choose", choices=["0", "1", "2", "3", "4", "5", "6"])

            if choice == "1":
                keyword = await self.adapter.ask("Enter search keyword")
                if not keyword.strip():
                    self.adapter.print("[red]Keyword cannot be empty.[/]")
                    continue
                self.adapter.print(f"[yellow]Searching for '{keyword}'...[/]")
                results = await search.search_groups(client, keyword)
                if not results:
                    self.adapter.print("[red]No groups found.[/]")
                    continue
                for i, g in enumerate(results, 1):
                    self.adapter.print(f"  {i}. {g['title']} (@{g['username']}) — {g['members']} members")
                sel = await self.adapter.ask("Select groups (comma-separated or 'all')")
                if sel.strip().lower() == "all":
                    selected = results
                else:
                    try:
                        indices = [int(x.strip()) - 1 for x in sel.split(",")]
                        selected = [results[i] for i in indices if 0 <= i < len(results)]
                    except (ValueError, IndexError):
                        self.adapter.print("[red]Invalid selection.[/]")
                        continue
                if selected:
                    confirm = await self.adapter.ask(f"Join {len(selected)} group(s)? [y/n]")
                    if confirm.strip().lower() in ("y", "yes"):
                        await search.join_groups(client, selected, self.adapter, db=database, rate_limiter=rate_limiter)

            elif choice == "2":
                all_groups = database.get_all_groups()
                if not all_groups:
                    self.adapter.print("[red]No joined groups. Search & join first.[/]")
                    continue
                for i, g in enumerate(all_groups, 1):
                    self.adapter.print(f"  {i}. {g['title']} (@{g.get('username') or '—'})")
                sel = await self.adapter.ask("Select targets (comma-separated or 'all')")
                if sel.strip().lower() == "all":
                    selected = all_groups
                else:
                    try:
                        indices = [int(x.strip()) - 1 for x in sel.split(",")]
                        selected = [all_groups[i] for i in indices if 0 <= i < len(all_groups)]
                    except (ValueError, IndexError):
                        self.adapter.print("[red]Invalid selection.[/]")
                        continue
                if selected:
                    text = await self.adapter.ask("Enter message or t.me link")
                    if text.strip():
                        confirm = await self.adapter.ask(f"Send to {len(selected)} group(s)? [y/n]")
                        if confirm.strip().lower() in ("y", "yes"):
                            await blast.blast_message(client, selected, text, self.adapter, db=database, rate_limiter=rate_limiter)

            elif choice == "3":
                await groups.fetch_all_groups(client, self.adapter, db=database, rate_limiter=rate_limiter)

            elif choice == "4":
                # Reimplement find_and_leave_restricted using adapter (avoids blocking Prompt.ask)
                await self._find_and_leave_restricted(client, database, rate_limiter)

            elif choice == "5":
                await groups.check_spam_status(client, self.adapter, db=database, rate_limiter=rate_limiter)

            elif choice == "6":
                await groups.check_premium_status(client, self.adapter, db=database, rate_limiter=rate_limiter)

            elif choice == "0":
                self.adapter.print("[yellow]Disconnecting...[/]")
                break

    async def _find_and_leave_restricted(self, client, database, rate_limiter):
        """Textual-compatible version of find_and_leave_restricted."""
        from pyrogram import enums
        from pyrogram.errors import RPCError
        from groups import _check_can_send

        self.adapter.print("[yellow]Fetching groups...[/]")

        all_groups = []
        async for dialog in client.get_dialogs():
            chat = dialog.chat
            if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL):
                all_groups.append(chat)

        if not all_groups:
            self.adapter.print("[red]No groups found.[/]")
            return

        self.adapter.print(f"[yellow]Checking send permissions for {len(all_groups)} groups...[/]")

        restricted = []
        for i, chat in enumerate(all_groups):
            try:
                if not await _check_can_send(client, chat, rate_limiter=rate_limiter):
                    restricted.append(chat)
            except Exception:
                pass
            if (i + 1) % 10 == 0:
                self.adapter.print(f"[dim]Checked {i+1}/{len(all_groups)}...[/]")

        if not restricted:
            self.adapter.print("[green]All groups allow sending messages.[/]")
            return

        self.adapter.print(f"\n[yellow]Found {len(restricted)} restricted group(s):[/]")
        for i, chat in enumerate(restricted, 1):
            uname = f"@{chat.username}" if chat.username else "—"
            self.adapter.print(f"  {i}. {chat.title or '—'} ({uname})")

        sel = await self.adapter.ask("Select groups to leave (comma-separated or 'all')")
        if sel.strip().lower() == "all":
            selected = restricted
        else:
            try:
                indices = [int(x.strip()) - 1 for x in sel.split(",")]
                selected = [restricted[i] for i in indices if 0 <= i < len(restricted)]
            except (ValueError, IndexError):
                self.adapter.print("[red]Invalid selection.[/]")
                return

        if not selected:
            self.adapter.print("[red]No groups selected.[/]")
            return

        confirm = await self.adapter.ask(f"Leave {len(selected)} group(s)? [y/n]")
        if confirm.strip().lower() not in ("y", "yes"):
            return

        left = 0
        for i, chat in enumerate(selected):
            try:
                await rate_limiter.call(lambda c=chat: client.leave_chat(c.id), self.adapter)
                database.remove_group(chat.id)
                self.adapter.print(f"  [green]✓[/] Left: {chat.title}")
                left += 1
            except RPCError as e:
                self.adapter.print(f"  [red]✗ Failed: {chat.title} — {e}[/]")

        self.adapter.print(f"\n[green]Left {left}/{len(selected)} groups.[/]")

    @on(Input.Submitted, "#input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Forward input to the OutputAdapter."""
        value = event.value
        event.input.clear()
        event.input.placeholder = "Enter command..."
        if self.adapter and self.adapter.waiting_for_input:
            # Echo the input
            rich_log = self.query_one("#output", RichLog)
            rich_log.write(f"[bold]> {value}[/]")
            self.adapter.submit_input(value)
        else:
            # Handle reconnect command
            if value.strip().lower() == "reconnect" and self._status == "disconnected":
                # Guard: don't reconnect if a worker is still running
                has_running = any(not w.is_finished for w in self.workers)
                if not has_running:
                    rich_log = self.query_one("#output", RichLog)
                    rich_log.write("[bold]> reconnect[/]")
                    self._start_instance()
                else:
                    rich_log = self.query_one("#output", RichLog)
                    rich_log.write("[dim]Worker still running, please wait...[/]")
            elif value.strip():
                rich_log = self.query_one("#output", RichLog)
                rich_log.write("[dim]No prompt active[/]")
