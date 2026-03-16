"""TeleX Multi-Instance Installer — Textual TUI App."""

import re
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, TabbedContent, TabPane, Static

# Ensure TeleX project root is importable
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from installer.instance_manager import load_instances, remove_instance
from installer.widgets.instance_tab import InstanceTab
from installer.widgets.setup_screen import SetupScreen
from installer.widgets.confirm_screen import ConfirmScreen


class TeleXApp(App):
    """Multi-instance TeleX manager with tabbed UI."""

    TITLE = "TeleX Multi-Instance"
    CSS = """
    Screen {
        background: $surface;
    }
    #welcome {
        width: 100%;
        height: 100%;
        content-align: center middle;
        text-align: center;
    }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_instance", "New Instance"),
        Binding("ctrl+d", "delete_instance", "Delete Instance"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield TabbedContent(id="tabs")
        yield Footer()

    def on_mount(self) -> None:
        """Load saved instances and create tabs."""
        instances = load_instances()
        if not instances:
            self._show_welcome()
        else:
            for config in instances:
                self._add_instance_tab(config)

    def _show_welcome(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        pane = TabPane("Welcome", id="welcome-tab")
        pane.compose_add_child(
            Static(
                "[bold cyan]TeleX Multi-Instance[/]\n\n"
                "No instances configured yet.\n"
                "Press [bold]Ctrl+N[/] to add a new instance.",
                id="welcome",
            )
        )
        tabs.add_pane(pane)

    def __init__(self):
        super().__init__()
        # Maps tab_id -> instance name for deletion
        self._tab_to_name: dict[str, str] = {}

    def _add_instance_tab(self, config) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        # Remove welcome tab if present
        try:
            tabs.remove_pane("welcome-tab")
        except Exception:
            pass
        # Sanitize name to valid Textual ID (letters, numbers, hyphens, underscores only)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", config.name)
        tab_id = f"tab-{safe_name}"
        self._tab_to_name[tab_id] = config.name
        pane = TabPane(config.name, id=tab_id)
        pane.compose_add_child(InstanceTab(config))
        tabs.add_pane(pane)

    def action_new_instance(self) -> None:
        """Open the setup screen for adding a new instance."""
        self.push_screen(SetupScreen(), callback=self._on_setup_complete)

    def _on_setup_complete(self, config) -> None:
        if config is not None:
            self._add_instance_tab(config)
            self.notify(f"Instance '{config.name}' created")

    def action_delete_instance(self) -> None:
        """Delete the currently active instance tab."""
        tabs = self.query_one("#tabs", TabbedContent)
        active_pane = tabs.active_pane
        if active_pane is None or active_pane.id == "welcome-tab":
            self.notify("No instance selected", severity="warning")
            return
        name = self._tab_to_name.get(active_pane.id)
        if not name:
            return
        self.push_screen(
            ConfirmScreen(f"[bold red]Delete instance '{name}'?[/]\n\nThis removes the session, database, and all data."),
            callback=lambda confirmed: self._on_delete_confirmed(confirmed, active_pane.id, name),
        )

    def _on_delete_confirmed(self, confirmed: bool, tab_id: str, name: str) -> None:
        if not confirmed:
            return
        try:
            remove_instance(name)
        except ValueError as e:
            self.notify(str(e), severity="error")
            return

        tabs = self.query_one("#tabs", TabbedContent)
        try:
            tabs.remove_pane(tab_id)
        except Exception:
            pass
        self._tab_to_name.pop(tab_id, None)
        self.notify(f"Instance '{name}' deleted")

        # Show welcome if no instances left
        if not self._tab_to_name:
            self._show_welcome()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Focus the Input widget in the newly activated tab."""
        try:
            inp = event.pane.query_one(Input)
            inp.focus()
        except Exception:
            pass

    def action_quit(self) -> None:
        self.exit()
