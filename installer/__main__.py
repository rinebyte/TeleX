"""Entry point: python -m installer"""

import asyncio
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

from installer.app import TeleXApp


def main():
    app = TeleXApp()
    app.run()


if __name__ == "__main__":
    main()
