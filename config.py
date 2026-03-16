import os
from dotenv import load_dotenv


def parse_proxy(url: str) -> dict | None:
    """Parse proxy URL into Pyrogram proxy dict.

    Supported formats:
      socks5://host:port
      socks5://user:pass@host:port
      socks4://host:port
      http://host:port
      http://user:pass@host:port
    """
    if not url:
        return None
    from urllib.parse import urlparse
    p = urlparse(url)
    scheme = (p.scheme or "").lower()
    scheme_map = {"socks5": "SOCKS5", "socks4": "SOCKS4", "http": "HTTP"}
    if scheme not in scheme_map:
        raise ValueError(
            f"Unsupported proxy scheme '{scheme}'. Use socks5://, socks4://, or http://"
        )
    proxy = {
        "scheme": scheme_map[scheme],
        "hostname": p.hostname,
        "port": p.port,
    }
    if p.username:
        proxy["username"] = p.username
    if p.password:
        proxy["password"] = p.password
    return proxy


def load_config(env_path=None) -> dict:
    """Load config from a .env file and return a config dict.

    If env_path is None, uses the default .env in cwd.
    """
    if env_path:
        load_dotenv(env_path, override=True)
    else:
        load_dotenv()

    api_id = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    phone = os.getenv("PHONE_NUMBER", "").strip()
    proxy_url = os.getenv("PROXY_URL", "").strip()

    if not api_id or not api_hash or not phone:
        raise ValueError(
            "Missing credentials. Set API_ID, API_HASH, and PHONE_NUMBER in .env"
        )

    return {
        "API_ID": int(api_id),
        "API_HASH": api_hash,
        "PHONE_NUMBER": phone,
        "PROXY_URL": proxy_url,
        "PROXY": parse_proxy(proxy_url),
    }


# --- Standalone globals (backward compatible) ---
load_dotenv()

API_ID = os.getenv("API_ID", "").strip()
API_HASH = os.getenv("API_HASH", "").strip()
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "").strip()

PROXY_URL = os.getenv("PROXY_URL", "").strip()  # socks5://user:pass@host:port

if not API_ID or not API_HASH or not PHONE_NUMBER:
    raise ValueError(
        "Missing credentials. Set API_ID, API_HASH, and PHONE_NUMBER in .env"
    )

API_ID = int(API_ID)

PROXY = parse_proxy(PROXY_URL)

# Delays in seconds
BLAST_DELAY = 3
JOIN_DELAY = 5
SLEEP_THRESHOLD = 60

# Anti-rate-limit settings
MAX_CONCURRENT_REQUESTS = 3    # Global semaphore — max in-flight API calls
MAX_RETRIES = 4                # Retry attempts with exponential backoff
BACKOFF_BASE = 2.0             # 2^attempt seconds base delay
JITTER_RANGE = (0.5, 2.0)     # Random multiplier on all delays
INITIAL_JOIN_BATCH_SIZE = 10   # Starting join batch size
MIN_BATCH_SIZE = 2             # Floor for adaptive batch sizing
BLAST_BATCH_SIZE = 5           # Concurrent messages per blast batch
ADAPTIVE_COOLDOWN = 30         # Seconds of no floods before decreasing delays
ADAPTIVE_MULTIPLIER_INC = 1.5  # Delay multiplier increase on flood
ADAPTIVE_MULTIPLIER_DEC = 0.9  # Delay multiplier decrease on cooldown
ADAPTIVE_MULTIPLIER_MAX = 5.0  # Cap for delay multiplier
