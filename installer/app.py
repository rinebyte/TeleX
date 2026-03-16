"""TeleX Multi-Instance Installer — Textual TUI App."""

import re
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane, Static

# Ensure TeleX project root is importable
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from installer.instance_manager import load_instances
from installer.widgets.instance_tab import InstanceTab
from installer.widgets.setup_screen import SetupScreen


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
        Binding("n", "new_instance", "New Instance"),
        Binding("q", "quit", "Quit"),
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
                "Press [bold]n[/] to add a new instance.",
                id="welcome",
            )
        )
        tabs.add_pane(pane)

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

    def action_quit(self) -> None:
        self.exit()
