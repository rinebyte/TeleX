"""Entry point: python -m installer"""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure TeleX project root is importable
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Pyrogram needs an event loop at import time
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# Configure logging to file
_log_dir = Path.home() / ".telex"
_log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(_log_dir / "installer.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from installer.app import TeleXApp


def main():
    logging.info("TeleX installer starting")
    app = TeleXApp()
    app.run()
    logging.info("TeleX installer exited")


if __name__ == "__main__":
    main()
