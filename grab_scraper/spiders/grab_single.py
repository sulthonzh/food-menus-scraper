"""Grab Food single merchant spider — browser for discovery, API for menu.

Architecture:
  1. Playwright loads the Grab Food listing page to get WAF cookies.
  2. Cookies + headers are extracted from the browser context.
  3. Scrapy hits the merchant menu API directly (no browser per restaurant).
  4. Falls back to intercepting the guest API from browser if direct API fails.
"""

import json
import os
import re
import logging

import scrapy
from urllib.parse import urlparse
from playwright.async_api import async_playwright


logger = logging.getLogger(__name__)

DEFAULT_URL = (
    "https://food.grab.com/id/id/restaurant/"
    "ayam-katsu-katsunami-lokarasa-citraland-delivery/6-C7EYGBJDME3JRN"
)

LISTING_URL = "https://food.grab.com/id/id/restaurants"

MERCHANT_ID_RE = re.compile(r"/([A-Z0-9]{4,})$")

GUEST_API = "https://portal.grab.com/foodweb/guest/v2/merchants"
PROXY_API = "https://food.grab.com/proxy/foodweb/v2/order/merchants"

GUEST_API_PATTERN = "/guest/v2/merchants/"

ENV_COOKIES = os.environ.get("GRAB_COOKIES", "")
ENV_GFC_SESSION = os.environ.get("GRAB_X_GFC_SESSION", "")
ENV_HYDRA_JWT = os.environ.get("GRAB_X_HYDRA_JWT", "")
ENV_APP_VERSION = os.environ.get("GRAB_X_APP_VERSION", "rnU80FF3gt8ojhFqnw9X4")

UA_STRING = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)


def _extract_merchant_id(url):
    path = urlparse(url).path.rstrip("/")
    m = MERCHANT_ID_RE.search(path)
    if m:
        return m.group(1)
    parts = path.split("/")
    return parts[-1] if parts else None


def _format_price(minor_units):
    if not minor_units:
        return "Rp0"
    major = minor_units / 100
    return f"Rp{major:,.0f}".replace(",", ".")


def _parse_cookie_string(raw):
    cookies = {}
    for pair in raw.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


async def _bootstrap_via_browser(latlng):
    """Load the listing page in headless Chromium to get WAF cookies.

    Returns (cookies_dict, intercepted_data_or_None).
    The cookies can be reused for direct API calls. If the listing page
    happens to trigger a merchant API call, intercepted_data contains
    the raw JSON text.
    """
    captured = {}
    captured_merchant = {}

    async def _on_response(response):
        if response.status != 200:
            return
        url = response.url
        # Capture any WAF/session cookies from the listing API calls
        if "/guest/v2/" in url or "foodweb" in url:
            captured["response_headers"] = dict(response.headers)
            try:
                captured["raw"] = await response.text()
                captured["url"] = url
            except Exception:
                pass
        # If a merchant API response happens, capture it too
        if GUEST_API_PATTERN in url:
            try:
                captured_merchant["data"] = await response.text()
            except Exception:
                pass

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=UA_STRING,
            locale="id-ID",
            viewport={"width": 1440, "height": 900},
        )

        # Inject location cookie so Grab renders restaurant content
        lat, lng = latlng.split(",")
        await ctx.add_cookies([{
            "name": "location",
            "value": json.dumps({
                "latitude": float(lat),
                "longitude": float(lng),
            }),
            "domain": ".grab.com",
            "path": "/",
        }])

        page = await ctx.new_page()
        page.on("response", _on_response)

        # Try loading the specific restaurant page first
        # This triggers the merchant guest API call during hydration
        restaurant_url = captured.get("restaurant_url", "")

        # Also load listing page to get WAF cookies
        logger.info("loading listing page to bootstrap session: %s", LISTING_URL)
        await page.goto(LISTING_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)

        # Now extract cookies from browser context
        browser_cookies = await ctx.cookies()

        await browser.close()

    # Convert browser cookies to dict for Scrapy
    cookies_dict = {}
    for c in browser_cookies:
        cookies_dict[c["name"]] = c["value"]

    intercepted_merchant = captured_merchant.get("data")

    return cookies_dict, intercepted_merchant


async def _scrape_menu_via_browser(page_url, latlng):
    """Load a restaurant page in headless Chromium, intercept the guest
    API response during hydration, and return the raw merchant JSON."""
    result = {}

    async def _catch_guest_api(response):
        if GUEST_API_PATTERN in response.url and response.status == 200:
            try:
                result["data"] = await response.text()
                result["url"] = response.url
            except Exception:
                pass

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=UA_STRING,
            locale="id-ID",
            viewport={"width": 1440, "height": 900},
        )
        page = await ctx.new_page()

        lat, lng = latlng.split(",")
        await ctx.add_cookies([{
            "name": "location",
            "value": json.dumps({"latitude": float(lat), "longitude": float(lng)}),
            "domain": ".grab.com",
            "path": "/",
        }])

        page.on("response", _catch_guest_api)

        logger.info("navigating to %s", page_url)
        await page.goto(page_url, wait_until="networkidle", timeout=90000)
        await page.wait_for_timeout(8000)

        await browser.close()

    if "data" not in result:
        logger.warning("guest API was not intercepted during page load")
        return None

    logger.info("intercepted guest API response (%d chars)", len(result["data"]))
    return result["data"]


class GrabSingleMerchantSpider(scrapy.Spider):
    name = "grab_single"

    custom_settings = {
        "FEEDS": {
            "output/%(name)s_%(time)s.csv": {
                "format": "csv",
                "overwrite": True,
                "fields": [
                    "outlet_name", "category_name", "menu_name",
                    "menu_description", "original_price", "promo_price",
                    "promo_nominal", "promo_percentage", "availability",
                ],
            },
        },
    }

    def __init__(self, url=None, latlng="-6.1825,106.8347", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.latlng = latlng
        self.target_url = url or DEFAULT_URL
        self.merchant_id = _extract_merchant_id(self.target_url)
        if not self.merchant_id:
            raise ValueError(f"could not extract merchant id from: {self.target_url}")

    async def start(self):
        # Path 1: env-var cookies provided — hit proxy API directly
        env_cookies = _parse_cookie_string(ENV_COOKIES) if ENV_COOKIES else {}
        if env_cookies:
            self.logger.info("using env cookies for proxy API")
            yield scrapy.Request(
                f"{PROXY_API}/{self.merchant_id}?latlng={self.latlng}",
                headers=self._build_api_headers(),
                cookies=env_cookies,
                callback=self.parse_merchant,
                meta={"merchant_id": self.merchant_id},
                dont_filter=True,
            )
            return

        # Path 2: browser bootstrap — load listing to get cookies, then API
        self.logger.info(
            "bootstrapping session via browser (listing → API for %s)",
            self.merchant_id,
        )
        browser_cookies, intercepted = await _bootstrap_via_browser(self.latlng)

        if not browser_cookies:
            self.logger.warning("no cookies from browser, falling back to full page intercept")
            raw_json = await _scrape_menu_via_browser(self.target_url, self.latlng)
            if raw_json:
                try:
                    data = json.loads(raw_json)
                    for item in self._parse_menu_data(data):
                        yield item
                except json.JSONDecodeError:
                    self.logger.error("bad json from intercepted response")
            return

        # If browser already captured the merchant data, use it
        if intercepted:
            self.logger.info("using intercepted merchant data from browser")
            try:
                data = json.loads(intercepted)
                for item in self._parse_menu_data(data):
                    yield item
                return
            except json.JSONDecodeError:
                self.logger.warning("intercepted data was bad json, trying API")

        # Use browser cookies to hit the guest API directly
        self.logger.info(
            "got %d cookies from browser, hitting guest API for %s",
            len(browser_cookies),
            self.merchant_id,
        )
        yield scrapy.Request(
            f"{GUEST_API}/{self.merchant_id}?latlng={self.latlng}",
            headers=self._build_api_headers(),
            cookies=browser_cookies,
            callback=self.parse_merchant,
            meta={"merchant_id": self.merchant_id},
            dont_filter=True,
            errback=self.errback_fallback_to_browser,
        )

    def parse_merchant(self, response):
        mid = response.meta["merchant_id"]

        if response.status != 200:
            self.logger.warning("API returned status %d for %s", response.status, mid)
            return

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError:
            self.logger.error("bad json from %s (status %s)", mid, response.status)
            return

        # Check if the response has the expected structure
        merchant = data.get("merchant")
        if not merchant:
            self.logger.warning("no 'merchant' key in API response for %s", mid)
            return

        for item in self._parse_menu_data(data):
            yield item

    async def errback_fallback_to_browser(self, failure):
        """If the API call fails, fall back to full browser interception."""
        self.logger.warning(
            "API call failed for %s, falling back to browser intercept",
            self.merchant_id,
        )
        raw_json = await _scrape_menu_via_browser(self.target_url, self.latlng)
        if raw_json:
            try:
                data = json.loads(raw_json)
                for item in self._parse_menu_data(data):
                    yield item
            except json.JSONDecodeError:
                self.logger.error("bad json from fallback browser intercept")

    def _parse_menu_data(self, data):
        merchant = data.get("merchant") or {}
        merchant_name = merchant.get("name", "Unknown")
        categories = (merchant.get("menu") or {}).get("categories") or []

        if not categories:
            self.logger.info("no menu for %s", merchant_name)
            return

        seen = set()
        total = 0

        for cat in categories:
            cat_name = cat.get("name", "Uncategorized")
            if cat_name in ("Pesanan Terakhirmu", "Untukmu"):
                continue

            for item in cat.get("items", []):
                item_id = item.get("ID", "")
                if item_id in seen:
                    continue
                seen.add(item_id)

                price_minor = item.get("priceInMinorUnit", 0)
                discounted_minor = item.get("discountedPriceInMin", price_minor)

                original_price = _format_price(price_minor)
                promo_price = None
                promo_nominal = None
                promo_percentage = None
                if discounted_minor and discounted_minor != price_minor:
                    promo_price = _format_price(discounted_minor)
                    diff = price_minor - discounted_minor
                    promo_nominal = _format_price(diff)
                    pct = round((diff / price_minor) * 100)
                    promo_percentage = f"{pct}%"

                availability = "Available" if item.get("available", True) else "Sold Out"

                total += 1
                yield {
                    "outlet_name": merchant_name,
                    "category_name": cat_name,
                    "menu_name": item.get("name", ""),
                    "menu_description": item.get("description", "") or "",
                    "original_price": original_price,
                    "promo_price": promo_price or "",
                    "promo_nominal": promo_nominal or "",
                    "promo_percentage": promo_percentage or "",
                    "availability": availability,
                }

        self.logger.info("scraped %d items from %s (%s)", total, merchant_name, self.merchant_id)

    def _build_api_headers(self):
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "id",
            "x-country-code": "ID",
            "x-gfc-country": "ID",
            "user-agent": UA_STRING,
            "sec-ch-ua": '"Chromium";v="145", "Not/A)Brand";v="8"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "referer": "https://food.grab.com/id/id/",
            "x-grab-web-app-version": ENV_APP_VERSION,
        }
        if ENV_GFC_SESSION:
            headers["x-gfc-session"] = ENV_GFC_SESSION
        if ENV_HYDRA_JWT:
            headers["x-hydra-jwt"] = ENV_HYDRA_JWT
        return headers
