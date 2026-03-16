# TeleX

Telegram userbot for searching, joining, and blasting messages to groups — with multi-account support.

## Features

- **Search & Join** — Search public groups by keyword and batch-join
- **Blast Message** — Send text or forward messages to multiple groups
- **Group Management** — Fetch all groups, find restricted groups, auto-leave
- **Spam Check** — Check account status via @SpamBot
- **Premium Check** — Check Telegram Premium status
- **Live Stats** — Real-time RAM, CPU, and network monitoring
- **Adaptive Rate Limiting** — Auto-adjusts delays and batch sizes on FloodWait
- **Multi-Instance** — Run multiple accounts simultaneously with tabbed TUI

## Requirements

- Python 3.10+
- Telegram API credentials from [my.telegram.org](https://my.telegram.org)

## Setup

```bash
git clone git@github.com:rinebyte/TeleX.git
cd TeleX
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your credentials:

```env
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890
PHONE_NUMBER=+628123456789
PROXY_URL=socks5://host:port   # optional
```

## Usage

### Standalone (single account)

```bash
python main.py
```

### Multi-Instance (multiple accounts)

```bash
python -m installer
```

This opens a tabbed TUI where you can:

- Press `n` to add a new account
- Each account runs in its own tab with isolated session & database
- Instance configs are saved at `~/.telex/instances.json`
- Press `q` to quit

## Project Structure

```
TeleX/
├── main.py              # Standalone entry point
├── config.py            # Config loader (.env)
├── db.py                # SQLite database (groups registry)
├── search.py            # Search & join groups
├── blast.py             # Blast messages to groups
├── groups.py            # Group management utilities
├── ratelimit.py         # Adaptive rate limiter
├── stats.py             # Live process stats
├── models.py            # Type definitions
├── requirements.txt
├── installer/
│   ├── __main__.py      # Multi-instance entry point
│   ├── app.py           # Textual TUI app
│   ├── instance_manager.py  # CRUD for instances
│   ├── output_adapter.py    # Console/RichLog bridge
│   └── widgets/
│       ├── instance_tab.py  # Per-account tab
│       └── setup_screen.py  # New account modal
```

## Proxy Support

Supported proxy formats:

```
socks5://host:port
socks5://user:pass@host:port
socks4://host:port
http://host:port
http://user:pass@host:port
```

## License

MIT
