import asyncio
import logging
import random
import time

from pyrogram.errors import FloodWait, RPCError

from config import (
    MAX_CONCURRENT_REQUESTS,
    MAX_RETRIES,
    BACKOFF_BASE,
    JITTER_RANGE,
    INITIAL_JOIN_BATCH_SIZE,
    MIN_BATCH_SIZE,
    ADAPTIVE_COOLDOWN,
    ADAPTIVE_MULTIPLIER_INC,
    ADAPTIVE_MULTIPLIER_DEC,
    ADAPTIVE_MULTIPLIER_MAX,
)

log = logging.getLogger("telex.ratelimit")


class RateLimitState:
    def __init__(self):
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self._delay_multiplier = 1.0
        self._batch_size = INITIAL_JOIN_BATCH_SIZE
        self._last_flood_time = 0.0

    @property
    def batch_size(self) -> int:
        return self._batch_size

    async def call(self, coro_factory, console=None):
        """Execute an API call with semaphore, retries, and exponential backoff.

        coro_factory: callable returning a fresh coroutine each time,
                      e.g. lambda: app.join_chat(username)
        """
        async with self._semaphore:
            last_exc = None
            for attempt in range(MAX_RETRIES):
                try:
                    result = await coro_factory()
                    self._report_success()
                    return result
                except FloodWait as e:
                    last_exc = e
                    jitter = random.uniform(*JITTER_RANGE)
                    wait = e.value + jitter
                    self._report_flood(e.value, console)
                    log.warning(
                        "Retry %d/%d after FloodWait %ds (sleeping %.1fs)",
                        attempt + 1, MAX_RETRIES, e.value, wait,
                    )
                    if console:
                        console.print(
                            f"  [yellow]⏳ FloodWait {e.value}s "
                            f"(attempt {attempt + 1}/{MAX_RETRIES}), "
                            f"sleeping {wait:.1f}s...[/]"
                        )
                    await asyncio.sleep(wait)
                except RPCError:
                    # Telegram API errors (403, SlowmodeWait, etc.) won't resolve on retry
                    raise
                except Exception:
                    # Transient/network errors: apply backoff then re-raise on last attempt
                    if attempt == MAX_RETRIES - 1:
                        raise
                    backoff = (BACKOFF_BASE ** attempt) * random.uniform(*JITTER_RANGE)
                    await asyncio.sleep(backoff)

            # All retries exhausted — re-raise last FloodWait
            if last_exc is not None:
                raise last_exc

    def get_delay(self, base_delay: float) -> float:
        """Return an adaptive, jittered delay for use between batches."""
        return base_delay * self._delay_multiplier * random.uniform(*JITTER_RANGE)

    def _report_flood(self, wait_seconds: float, console=None):
        """Called when a FloodWait is encountered."""
        self._last_flood_time = time.monotonic()

        # Increase delay multiplier
        self._delay_multiplier = min(
            self._delay_multiplier * ADAPTIVE_MULTIPLIER_INC,
            ADAPTIVE_MULTIPLIER_MAX,
        )

        # Halve batch size (floor at MIN_BATCH_SIZE)
        self._batch_size = max(self._batch_size // 2, MIN_BATCH_SIZE)

        log.warning(
            "FloodWait %ds — multiplier=%.2f, batch=%d",
            wait_seconds, self._delay_multiplier, self._batch_size,
        )
        if console:
            console.print(
                f"  [yellow]⚠ Rate pressure: multiplier={self._delay_multiplier:.2f}, "
                f"batch_size={self._batch_size}[/]"
            )

    def _report_success(self):
        """Called after a successful API call to gradually recover parameters."""
        now = time.monotonic()
        elapsed = now - self._last_flood_time

        if self._last_flood_time == 0.0:
            return

        # After ADAPTIVE_COOLDOWN seconds of no floods: decrease multiplier
        if elapsed >= ADAPTIVE_COOLDOWN and self._delay_multiplier > 1.0:
            self._delay_multiplier = max(
                self._delay_multiplier * ADAPTIVE_MULTIPLIER_DEC, 1.0
            )
            log.info("Rate pressure easing — multiplier=%.2f", self._delay_multiplier)

        # After ADAPTIVE_COOLDOWN*2: slowly increase batch size
        if elapsed >= ADAPTIVE_COOLDOWN * 2:
            if self._batch_size < INITIAL_JOIN_BATCH_SIZE:
                self._batch_size += 1


rate_limiter = RateLimitState()
