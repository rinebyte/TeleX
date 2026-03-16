"""Per-instance tab: RichLog output + Input for menu interaction."""

import asyncio
import logging
import sys
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog, Static

# Ensure TeleX project root is importable
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from installer.instance_manager import InstanceConfig
from installer.output_adapter import OutputAdapter


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
        self.instance = None
        self._status = "disconnected"

    def compose(self) -> ComposeResult:
        yield Static(f"[dim]{self.config.name}[/] — disconnected", id="status-bar")
        yield RichLog(highlight=True, markup=True, wrap=True, id="output")
        yield Input(placeholder="Enter command...", id="input")

    def on_mount(self) -> None:
        rich_log = self.query_one("#output", RichLog)
        self.adapter = OutputAdapter(rich_log=rich_log)
        self._start_instance()

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

    @work(thread=False)
    async def _start_instance(self) -> None:
        """Start the TeleX instance as an async worker."""
        from config import load_config, parse_proxy, SLEEP_THRESHOLD
        from db import Database
        from ratelimit import RateLimitState
        from pyrogram import Client

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
            phone_number=self.config.phone,
            no_updates=True,
            sleep_threshold=SLEEP_THRESHOLD,
            **proxy_kwargs,
        )

        try:
            await client.start()
        except Exception as e:
            self.adapter.print(f"[red]Failed to start: {e}[/]")
            self._update_status("error", "red")
            return

        self._update_status("connected", "green")
        me = await client.get_me()
        self.adapter.print(
            f"[green]Logged in as {me.first_name or ''} (@{me.username or '—'})[/]"
        )

        if proxy:
            self.adapter.print(
                f"[cyan]Proxy:[/] {proxy['scheme']}://{proxy['hostname']}:{proxy['port']}"
            )

        # Run menu loop
        try:
            await self._menu_loop(client, database, rate_limiter)
        except Exception as e:
            self.adapter.print(f"[red]Error: {e}[/]")
        finally:
            try:
                await client.stop()
            except Exception:
                pass
            self._update_status("disconnected", "dim")

    async def _menu_loop(self, client, database, rate_limiter):
        """Interactive menu driven by the OutputAdapter."""
        import search
        import blast
        import groups

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
                await groups.find_and_leave_restricted(client, self.adapter, db=database, rate_limiter=rate_limiter)

            elif choice == "5":
                await groups.check_spam_status(client, self.adapter, db=database, rate_limiter=rate_limiter)

            elif choice == "6":
                await groups.check_premium_status(client, self.adapter, db=database, rate_limiter=rate_limiter)

            elif choice == "0":
                self.adapter.print("[yellow]Disconnecting...[/]")
                break

    @on(Input.Submitted, "#input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Forward input to the OutputAdapter."""
        value = event.value
        event.input.clear()
        if self.adapter and self.adapter.waiting_for_input:
            # Echo the input
            rich_log = self.query_one("#output", RichLog)
            rich_log.write(f"[bold]> {value}[/]")
            self.adapter.submit_input(value)
