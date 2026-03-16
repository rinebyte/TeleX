"""Generic confirmation modal."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmScreen(ModalScreen[bool]):
    """Simple yes/no confirmation dialog."""

    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-dialog {
        width: 50;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    #confirm-buttons {
        margin-top: 1;
        align: right middle;
        height: 3;
    }
    #confirm-buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(self._message)
            with Horizontal(id="confirm-buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Delete", variant="error", id="confirm")

    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm")
    def on_confirm(self) -> None:
        self.dismiss(True)
