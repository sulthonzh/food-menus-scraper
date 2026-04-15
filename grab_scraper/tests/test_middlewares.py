"""Tests for custom middlewares."""

import pytest
from unittest.mock import MagicMock
from scrapy.http import Request

from grab_scraper.middlewares import (
    AntiDetectionMiddleware,
    UserAgentRotationMiddleware,
)


class TestUserAgentRotationMiddleware:
    def setup_method(self):
        self.middleware = UserAgentRotationMiddleware()

    def test_adds_user_agent(self):
        request = Request("https://food.grab.com")
        result = self.middleware.process_request(request, None)
        assert result is None
        assert "User-Agent" in request.headers
        ua = request.headers["User-Agent"].decode()
        assert "Mozilla" in ua

    def test_different_uas_across_requests(self):
        uas = set()
        for _ in range(20):
            request = Request("https://food.grab.com")
            self.middleware.process_request(request, None)
            uas.add(request.headers["User-Agent"].decode())
        assert len(uas) > 1


class TestAntiDetectionMiddleware:
    def setup_method(self):
        self.middleware = AntiDetectionMiddleware()

    def test_adds_security_headers(self):
        request = Request("https://food.grab.com")
        result = self.middleware.process_request(request, None)
        assert result is None
        assert "Sec-Ch-Ua" in request.headers
        assert "Sec-Fetch-Dest" in request.headers

    def test_adds_upgrade_header(self):
        request = Request("https://food.grab.com")
        self.middleware.process_request(request, None)
        assert request.headers.get("Upgrade-Insecure-Requests") == b"1"
