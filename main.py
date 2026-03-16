import asyncio
import logging
from pathlib import Path

# Python 3.14+ removed implicit event loop creation; Pyrogram needs one at import time
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.prompt import Prompt

from config import API_ID, API_HASH, PHONE_NUMBER, SLEEP_THRESHOLD, PROXY, load_config, parse_proxy
from db import Database
from ratelimit import RateLimitState
import db
import search
import blast
import groups
import stats

console = Console()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(console=console, show_path=False, markup=True, level=logging.INFO),
        logging.FileHandler("telex.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("telex")

BANNER = """[bold cyan]
 ████████╗███████╗██╗     ███████╗██╗  ██╗
 ╚══██╔══╝██╔════╝██║     ██╔════╝╚██╗██╔╝
    ██║   █████╗  ██║     █████╗   ╚███╔╝
    ██║   ██╔══╝  ██║     ██╔══╝   ██╔██╗
    ██║   ███████╗███████╗███████╗██╔╝ ██╗
    ╚═╝   ╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝
[/][dim]Telegram Userbot — Search · Join · Blast[/]"""


class TeleXInstance:
    """Bundles all per-instance state: config, db, rate_limiter, output."""

    def __init__(self, config: dict, work_dir: str = ".", output=None, session_name: str = "telex"):
        self.config = config
        self.work_dir = Path(work_dir)
        self.output = output or Console()
        self.session_name = session_name

        self.database = Database(str(self.work_dir / "telex.db"))
        self.rate_limiter = RateLimitState()
        self.client = None
        self._running = False

    async def start(self):
        """Initialize database and start Pyrogram client."""
        self.database.init_db()

        proxy = self.config.get("PROXY")
        proxy_kwargs = {"proxy": proxy} if proxy else {}
        self.client = Client(
            str(self.work_dir / self.session_name),
            api_id=self.config["API_ID"],
            api_hash=self.config["API_HASH"],
            phone_number=self.config["PHONE_NUMBER"],
            no_updates=True,
            sleep_threshold=SLEEP_THRESHOLD,
            **proxy_kwargs,
        )

        await self.client.start()
        self._running = True

        session_path = self.work_dir / f"{self.session_name}.session"
        if session_path.exists() and oct(session_path.stat().st_mode)[-2:] != "00":
            log.warning("Session file is world-readable — consider: chmod 600 %s", session_path)

        if proxy:
            self.output.print(
                f"[cyan]Proxy:[/] {proxy['scheme']}://{proxy['hostname']}:{proxy['port']}"
            )

        log.info("Logged in successfully")

    async def stop(self):
        """Stop the Pyrogram client."""
        if self.client and self._running:
            await self.client.stop()
            self._running = False

    async def run_menu_loop(self):
        """Run the interactive menu loop."""
        while True:
            try:
                self.output.print(
                    Panel(
                        "[1] Search & Join Groups\n"
                        "[2] Blast Message\n"
                        "[3] Fetch All Groups\n"
                        "[4] Find & Leave Restricted Groups\n"
                        "[5] Check Spam Status\n"
                        "[6] Check Premium Status\n"
                        "[7] Live Stats\n"
                        "[0] Exit",
                        title="[bold cyan]Menu[/]",
                        border_style="cyan",
                    )
                )

                choice = Prompt.ask("[cyan]Choose[/]", choices=["0", "1", "2", "3", "4", "5", "6", "7"])

                if choice == "1":
                    await search.search_and_join_menu(self.client, self.output, db=self.database, rate_limiter=self.rate_limiter)
                elif choice == "2":
                    await blast.blast_menu(self.client, self.output, db=self.database, rate_limiter=self.rate_limiter)
                elif choice == "3":
                    await groups.fetch_all_groups(self.client, self.output, db=self.database, rate_limiter=self.rate_limiter)
                elif choice == "4":
                    await groups.find_and_leave_restricted(self.client, self.output, db=self.database, rate_limiter=self.rate_limiter)
                elif choice == "5":
                    await groups.check_spam_status(self.client, self.output, db=self.database, rate_limiter=self.rate_limiter)
                elif choice == "6":
                    await groups.check_premium_status(self.client, self.output, db=self.database, rate_limiter=self.rate_limiter)
                elif choice == "7":
                    await stats.live_stats(self.output)
                elif choice == "0":
                    self.output.print("[yellow]Goodbye![/]")
                    break

                self.output.print()
            except KeyboardInterrupt:
                self.output.print("\n[yellow]Cancelled.[/]")
                continue


async def main():
    if API_ID is None:
        console.print("[red]Missing credentials. Set API_ID, API_HASH, and PHONE_NUMBER in .env[/]")
        return

    console.print(Panel(BANNER, border_style="cyan"))

    db.init_db()

    proxy_kwargs = {"proxy": PROXY} if PROXY else {}
    app = Client(
        "telex",
        api_id=API_ID,
        api_hash=API_HASH,
        phone_number=PHONE_NUMBER,
        no_updates=True,
        sleep_threshold=SLEEP_THRESHOLD,
        **proxy_kwargs,
    )

    # Warn if session file has overly permissive permissions
    session_path = Path("telex.session")
    if session_path.exists() and oct(session_path.stat().st_mode)[-2:] != "00":
        log.warning("Session file is world-readable — consider: chmod 600 telex.session")

    if PROXY:
        console.print(
            f"[cyan]Proxy:[/] {PROXY['scheme']}://{PROXY['hostname']}:{PROXY['port']}"
        )

    async with app:
        log.info("Logged in successfully")

        while True:
            try:
                console.print(
                    Panel(
                        "[1] Search & Join Groups\n"
                        "[2] Blast Message\n"
                        "[3] Fetch All Groups\n"
                        "[4] Find & Leave Restricted Groups\n"
                        "[5] Check Spam Status\n"
                        "[6] Check Premium Status\n"
                        "[7] Live Stats\n"
                        "[0] Exit",
                        title="[bold cyan]Menu[/]",
                        border_style="cyan",
                    )
                )

                choice = Prompt.ask("[cyan]Choose[/]", choices=["0", "1", "2", "3", "4", "5", "6", "7"])

                if choice == "1":
                    await search.search_and_join_menu(app, console)
                elif choice == "2":
                    await blast.blast_menu(app, console)
                elif choice == "3":
                    await groups.fetch_all_groups(app, console)
                elif choice == "4":
                    await groups.find_and_leave_restricted(app, console)
                elif choice == "5":
                    await groups.check_spam_status(app, console)
                elif choice == "6":
                    await groups.check_premium_status(app, console)
                elif choice == "7":
                    await stats.live_stats(console)
                elif choice == "0":
                    console.print("[yellow]Goodbye![/]")
                    break

                console.print()
            except KeyboardInterrupt:
                console.print("\n[yellow]Cancelled.[/]")
                continue


if __name__ == "__main__":
    asyncio.run(main())
