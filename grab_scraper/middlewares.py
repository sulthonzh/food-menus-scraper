"""Custom middlewares for resilience and anti-detection."""

import random
import logging

from twisted.internet import reactor
from twisted.internet.task import deferLater

from scrapy.downloadermiddlewares.retry import RetryMiddleware
from scrapy.utils.response import response_status_message

logger = logging.getLogger(__name__)

# Rotating user agents - Chrome/Firefox/Safari on various platforms
USER_AGENTS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    # Firefox on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    # Chrome on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


class UserAgentRotationMiddleware:
    """Rotate User-Agent on each request to avoid fingerprinting."""

    def __init__(self):
        self._agents = USER_AGENTS.copy()

    def process_request(self, request, spider=None):
        ua = random.choice(self._agents)
        request.headers["User-Agent"] = ua
        logger.debug("Rotated UA: %s", ua[:50])


class ExponentialBackoffRetryMiddleware(RetryMiddleware):
    """Retry with exponential backoff + jitter to handle transient failures."""

    def __init__(self, settings):
        super().__init__(settings)
        self.base_delay = float(settings.getfloat("RETRY_BASE_DELAY", 1.0))
        self.max_delay = float(settings.getfloat("RETRY_MAX_DELAY", 60.0))
        self.max_retries = settings.getint("RETRY_TIMES", 5)

    def _retry(self, request, reason, *, spider=None):
        retries = request.meta.get("retry_times", 0) + 1

        if retries > self.max_retries:
            logger.error(
                "Max retries (%d) exceeded for %s: %s",
                self.max_retries,
                request.url,
                reason,
            )
            return None

        delay = min(
            self.max_delay,
            (self.base_delay * (2 ** retries)) + random.uniform(0, 1),
        )

        logger.info(
            "Retrying %s in %.1fs (attempt %d/%d): %s",
            request.url,
            delay,
            retries,
            self.max_retries,
            reason,
        )

        retryreq = request.copy()
        retryreq.meta["retry_times"] = retries
        retryreq.dont_filter = True
        retryreq.priority = request.priority - self.max_retries

        deferred = deferLater(reactor, delay, lambda: retryreq)
        return deferred  # type: ignore[return-value]


class AntiDetectionMiddleware:
    """Add headers and measures to reduce bot detection risk."""

    def process_request(self, request, spider=None):
        # Mimic real browser headers
        request.headers["Sec-Ch-Ua"] = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
        request.headers["Sec-Ch-Ua-Mobile"] = "?0"
        request.headers["Sec-Ch-Ua-Platform"] = '"macOS"'
        request.headers["Sec-Fetch-Dest"] = "document"
        request.headers["Sec-Fetch-Mode"] = "navigate"
        request.headers["Sec-Fetch-Site"] = "none"
        request.headers["Sec-Fetch-User"] = "?1"
        request.headers["Upgrade-Insecure-Requests"] = "1"

        # Add random referer from popular sites
        if random.random() < 0.3:
            referers = [
                "https://www.google.com/",
                "https://www.google.co.id/",
                "https://food.grab.com/",
            ]
            request.headers["Referer"] = random.choice(referers)
