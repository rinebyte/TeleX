"""Adapter that bridges Rich Console.print() / Prompt.ask() to Textual RichLog / Input widgets."""

import asyncio

from rich.console import Console
from rich.text import Text


class OutputAdapter:
    """Wraps either a Console (standalone) or a RichLog (Textual) for unified output/input."""

    def __init__(self, rich_log=None, console=None):
        self._rich_log = rich_log
        self._console = console or Console()
        self._input_future: asyncio.Future | None = None
        self._input_prompt: str = ""

    def print(self, *args, **kwargs):
        if self._rich_log is not None:
            # RichLog.write() accepts Rich renderables or strings
            for arg in args:
                self._rich_log.write(arg)
            if not args:
                self._rich_log.write("")
        else:
            self._console.print(*args, **kwargs)

    async def ask(self, prompt: str, choices: list[str] | None = None) -> str:
        """Async prompt — in Textual mode, waits for Input widget submission."""
        if self._rich_log is not None:
            # Textual mode: show prompt and wait for input
            suffix = ""
            if choices:
                suffix = f" [{'/'.join(choices)}]"
            self._rich_log.write(Text(f"{prompt}{suffix}: ", style="cyan"))
            self._input_prompt = prompt

            loop = asyncio.get_event_loop()
            self._input_future = loop.create_future()
            result = await self._input_future
            self._input_future = None
            return result
        else:
            # Standalone mode: blocking prompt (run in executor to not block event loop)
            from rich.prompt import Prompt
            if choices:
                return Prompt.ask(prompt, choices=choices)
            return Prompt.ask(prompt)

    async def confirm(self, prompt: str) -> bool:
        """Async confirm — returns True/False."""
        result = await self.ask(f"{prompt} [y/n]")
        return result.strip().lower() in ("y", "yes")

    def submit_input(self, value: str):
        """Called by the Textual Input widget when user presses Enter."""
        if self._input_future and not self._input_future.done():
            self._input_future.set_result(value)

    @property
    def waiting_for_input(self) -> bool:
        return self._input_future is not None and not self._input_future.done()
