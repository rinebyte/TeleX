"""Modal screen for adding a new TeleX instance."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Input, Button, Label, Static

from installer.instance_manager import add_instance, InstanceConfig


class SetupScreen(ModalScreen[InstanceConfig | None]):
    """Modal dialog to configure a new TeleX instance."""

    CSS = """
    SetupScreen {
        align: center middle;
    }
    #setup-dialog {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #setup-dialog Label {
        margin-top: 1;
    }
    #setup-dialog Input {
        margin-bottom: 0;
    }
    #setup-dialog .error {
        color: $error;
        margin-top: 0;
    }
    #buttons {
        margin-top: 1;
        align: right middle;
        height: 3;
    }
    #buttons Button {
        margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-dialog"):
            yield Static("[bold cyan]Add New Instance[/]")

            yield Label("Instance Name")
            yield Input(placeholder="e.g. account1", id="name")

            yield Label("API ID")
            yield Input(placeholder="12345678", id="api_id")

            yield Label("API Hash")
            yield Input(placeholder="abcdef1234567890", id="api_hash")

            yield Label("Phone Number")
            yield Input(placeholder="+628123456789", id="phone")

            yield Label("Proxy URL (optional)")
            yield Input(placeholder="socks5://host:port", id="proxy_url")

            yield Static("", id="error-msg", classes="error")

            with Horizontal(id="buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Create", variant="primary", id="create")

    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#create")
    def on_create(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        api_id = self.query_one("#api_id", Input).value.strip()
        api_hash = self.query_one("#api_hash", Input).value.strip()
        phone = self.query_one("#phone", Input).value.strip()
        proxy_url = self.query_one("#proxy_url", Input).value.strip()

        error_widget = self.query_one("#error-msg", Static)

        if not name:
            error_widget.update("[red]Name is required[/]")
            return
        if not api_id or not api_id.isdigit():
            error_widget.update("[red]API ID must be a number[/]")
            return
        if not api_hash:
            error_widget.update("[red]API Hash is required[/]")
            return
        if not phone:
            error_widget.update("[red]Phone number is required[/]")
            return

        try:
            config = add_instance(name, int(api_id), api_hash, phone, proxy_url)
            self.dismiss(config)
        except ValueError as e:
            error_widget.update(f"[red]{e}[/]")
