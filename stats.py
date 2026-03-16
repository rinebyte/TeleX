import asyncio
import os

import psutil
from rich.live import Live
from rich.panel import Panel
from rich.table import Table


proc = psutil.Process(os.getpid())


def _fmt(b):
    """Format bytes to human-readable."""
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def _bar(percent, width=20):
    """Colored progress bar."""
    filled = int(width * percent / 100)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    if percent > 80:
        return f"[red]{bar}[/red]"
    elif percent > 50:
        return f"[yellow]{bar}[/yellow]"
    return f"[green]{bar}[/green]"


async def live_stats(console):
    """Display live-updating process stats for TeleX."""
    # Snapshot system-wide net counters for bandwidth delta
    net_start = psutil.net_io_counters()
    net_prev = net_start
    # Prime CPU measurement for the process
    proc.cpu_percent()

    total_mem = psutil.virtual_memory().total

    def build():
        nonlocal net_prev
        mem = proc.memory_info()
        cpu = proc.cpu_percent()
        mem_percent = mem.rss / total_mem * 100

        net = psutil.net_io_counters()
        dl_speed = net.bytes_recv - net_prev.bytes_recv
        ul_speed = net.bytes_sent - net_prev.bytes_sent
        total_dl = net.bytes_recv - net_start.bytes_recv
        total_ul = net.bytes_sent - net_start.bytes_sent
        net_prev = net

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Label", style="bold cyan", width=12)
        table.add_column("Value")

        table.add_row(
            "RAM",
            f"{_bar(mem_percent)} {_fmt(mem.rss)} ({mem_percent:.1f}%)",
        )
        table.add_row("CPU", f"{_bar(cpu)} {cpu:.1f}%")
        table.add_row(
            "↓ Download",
            f"{_fmt(dl_speed)}/s  Total: {_fmt(total_dl)}",
        )
        table.add_row(
            "↑ Upload",
            f"{_fmt(ul_speed)}/s  Total: {_fmt(total_ul)}",
        )

        return Panel(
            table,
            title="[bold cyan]TeleX Stats[/]",
            subtitle="[dim]Ctrl+C to go back[/]",
            border_style="cyan",
        )

    with Live(console=console, refresh_per_second=1) as live:
        try:
            while True:
                live.update(build())
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
