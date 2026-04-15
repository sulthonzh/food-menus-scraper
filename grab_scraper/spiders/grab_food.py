"""Grab Food listing and menu spider using Playwright interception."""

import json
import logging
import re
from importlib import import_module
from urllib.parse import urljoin

import scrapy
from scrapy_playwright.page import PageMethod

from grab_scraper.items import GrabMenuItem

logger = logging.getLogger(__name__)

try:
    Stealth = import_module("playwright_stealth").Stealth
except ModuleNotFoundError:
    class _FallbackStealth:
        def __init__(self, *args, **kwargs):
            pass

        async def apply_stealth_async(self, page):
            return None

    Stealth = _FallbackStealth

DEFAULT_LISTING_URL = "https://food.grab.com/id/id/restaurants"
LISTING_API_PATTERNS = (
    "foodweb/guest/v2/recommended/merchants",
    "foodweb/guest/v2/search",
)
MERCHANT_API_PATTERN = "foodweb/guest/v2/merchants/"
RESTAURANT_PATH_RE = re.compile(
    r"((?:/[a-z]{2}/[a-z]{2})?/restaurant/([^/?#]+)/([A-Z0-9-]+))",
    re.IGNORECASE,
)

_stealth = Stealth(
    navigator_languages_override=("id-ID", "id", "en-US", "en"),
    navigator_platform_override="MacIntel",
)


async def _apply_stealth(page, request):
    await _stealth.apply_stealth_async(page)
    page._grab_api_responses = []

    capture_mode = request.meta.get("grab_capture_mode")
    merchant_id = request.meta.get("grab_merchant_id")

    def _on_response(response):
        if response.status != 200:
            return

        response_url = response.url
        if capture_mode == "listing":
            if any(pattern in response_url for pattern in LISTING_API_PATTERNS):
                page._grab_api_responses.append(response)
            return

        if capture_mode == "merchant" and MERCHANT_API_PATTERN in response_url:
            if not merchant_id or merchant_id in response_url:
                page._grab_api_responses.append(response)

    page.on("response", _on_response)


class GrabFoodSpider(scrapy.Spider):
    name = "grab_food"
    allowed_domains = ["food.grab.com"]

    custom_settings = {
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 60000,
        "CONCURRENT_REQUESTS": 2,
        "DOWNLOAD_DELAY": 3,
    }

    def __init__(self, url=None, latlng=None, limit=None, max_pages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_url = url or DEFAULT_LISTING_URL
        self.override_latlng = latlng or None
        self.limit = self._parse_limit(limit)
        self.max_pages = self._parse_limit(max_pages) or 3
        self._seen_restaurant_ids = set()

    async def start(self):
        yield scrapy.Request(
            url=self.start_url,
            meta=self._build_playwright_meta("listing"),
            callback=self.parse_listing,
            errback=self.errback_close_page,
            dont_filter=True,
        )

    async def parse_listing(self, response):
        page = response.meta["playwright_page"]

        try:
            next_data = self._extract_next_data(response)
            latlng = self.override_latlng or self._extract_listing_latlng(next_data)
            restaurants = await self._discover_restaurants(page, response, latlng)

            if not restaurants:
                logger.error("No restaurants discovered from %s", response.url)
                return

            if self.limit is not None:
                restaurants = restaurants[: self.limit]

            logger.info("Discovered %d restaurants from %s", len(restaurants), response.url)

            for restaurant in restaurants:
                logger.info("Scraping restaurant %s (%s)", restaurant["id"], restaurant["url"])
                yield scrapy.Request(
                    url=restaurant["url"],
                    meta=self._build_playwright_meta(
                        "merchant",
                        merchant_id=restaurant["id"],
                        restaurant=restaurant,
                        latlng=restaurant.get("latlng") or latlng,
                    ),
                    callback=self.parse_restaurant,
                    errback=self.errback_close_page,
                    dont_filter=True,
                )
        finally:
            await page.close()

    async def parse_restaurant(self, response):
        page = response.meta["playwright_page"]
        restaurant = response.meta.get("grab_restaurant", {})
        restaurant_id = restaurant.get("id")
        restaurant_url = restaurant.get("url") or response.url

        try:
            payloads = await self._get_captured_api_payloads(page)
            merchant_payload = self._extract_merchant_payload(payloads, restaurant_id)

            if merchant_payload:
                items = self._parse_merchant_payload(merchant_payload, restaurant_url)
                logger.info(
                    "Extracted %d items from restaurant %s",
                    len(items),
                    restaurant_id or restaurant_url,
                )
                for item_data in items:
                    yield GrabMenuItem(**item_data)
                return

            logger.warning(
                "API interception failed for restaurant %s at %s, using DOM fallback",
                restaurant_id or "unknown",
                restaurant_url,
            )
            outlet_name = await self._extract_outlet_name(page, restaurant.get("name"))
            await self._scroll_to_load_all(page)
            items = await self._extract_dom_menu_data(page, outlet_name, restaurant_url)
            logger.info(
                "Extracted %d items from restaurant %s via DOM fallback",
                len(items),
                restaurant_id or restaurant_url,
            )
            for item_data in items:
                yield GrabMenuItem(**item_data)
        except Exception:
            logger.error(
                "Failed to scrape restaurant %s at %s",
                restaurant_id or "unknown",
                restaurant_url,
                exc_info=True,
            )
        finally:
            await page.close()

    def _build_playwright_meta(self, capture_mode, merchant_id=None, restaurant=None, latlng=None):
        wait_ms = 8000
        meta = {
            "playwright": True,
            "playwright_include_page": True,
            "playwright_page_init_callback": _apply_stealth,
            "playwright_page_methods": [
                PageMethod("wait_for_load_state", "domcontentloaded"),
                PageMethod("wait_for_timeout", wait_ms),
            ],
            "grab_capture_mode": capture_mode,
        }

        if capture_mode == "listing" and self.override_latlng:
            parts = self.override_latlng.split(",")
            if len(parts) == 2:
                try:
                    meta["playwright_context_kwargs"] = {
                        "geolocation": {
                            "latitude": float(parts[0].strip()),
                            "longitude": float(parts[1].strip()),
                        },
                        "permissions": ["geolocation"],
                    }
                except (ValueError, TypeError):
                    pass
        if merchant_id:
            meta["grab_merchant_id"] = merchant_id
        if restaurant:
            meta["grab_restaurant"] = restaurant
        if latlng:
            meta["grab_latlng"] = latlng
        return meta

    async def _discover_restaurants(self, page, response, latlng):
        all_restaurants = []

        restaurants = await self._try_api_discovery(page, response.url, latlng)
        if not restaurants:
            logger.warning(
                "Restaurant discovery API interception failed for %s, using DOM fallback",
                response.url,
            )
            restaurants = self._extract_restaurants_from_dom(response, latlng)

        all_restaurants.extend(restaurants)

        prev_count = len(all_restaurants)
        for page_num in range(self.max_pages - 1):
            prev_ids = {r["id"] for r in all_restaurants}
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2500)

            new_restaurants = await self._try_api_discovery(page, response.url, latlng)
            if not new_restaurants:
                try:
                    html = await page.content()
                    from scrapy.http import HtmlResponse as _HR
                    dom_response = _HR(url=response.url, body=html.encode(), encoding="utf-8")
                    new_restaurants = self._extract_restaurants_from_dom(dom_response, latlng)
                except Exception:
                    new_restaurants = []

            all_restaurants.extend(
                r for r in new_restaurants if r["id"] not in prev_ids
            )
            new_count = len(all_restaurants)
            if new_count == prev_count:
                break
            logger.info(
                "Pagination scroll %d: %d → %d restaurants",
                page_num + 2,
                prev_count,
                new_count,
            )
            prev_count = new_count

        return all_restaurants

    async def _try_api_discovery(self, page, page_url, latlng):
        payloads = await self._get_captured_api_payloads(page)
        restaurants = self._extract_restaurants_from_payloads(payloads, page_url, latlng)
        if restaurants:
            return restaurants
        for _ in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)
            payloads = await self._get_captured_api_payloads(page)
            restaurants = self._extract_restaurants_from_payloads(payloads, page_url, latlng)
            if restaurants:
                return restaurants
        return []

    async def _get_captured_api_payloads(self, page):
        payloads = []
        for api_response in getattr(page, "_grab_api_responses", []):
            try:
                payload = json.loads(await api_response.text())
            except Exception:
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    def _extract_restaurants_from_payloads(self, payloads, page_url, latlng):
        restaurants = []
        for payload in payloads:
            for merchant in self._find_merchants(payload):
                restaurant = self._build_restaurant_data(merchant, page_url, latlng)
                if restaurant:
                    restaurants.append(restaurant)
        return restaurants

    def _extract_restaurants_from_dom(self, response, latlng):
        restaurants = []
        for href in response.css('a[href*="/restaurant/"]::attr(href)').getall():
            match = RESTAURANT_PATH_RE.search(href)
            if not match:
                continue
            restaurant_id = match.group(3)
            if restaurant_id in self._seen_restaurant_ids:
                continue
            self._seen_restaurant_ids.add(restaurant_id)
            restaurants.append(
                {
                    "id": restaurant_id,
                    "slug": match.group(2),
                    "name": None,
                    "latlng": latlng,
                    "url": urljoin(response.url, href),
                }
            )
        return restaurants

    def _build_restaurant_data(self, merchant, page_url, fallback_latlng):
        merchant_id = merchant.get("id") or merchant.get("ID")
        if not merchant_id or merchant_id in self._seen_restaurant_ids:
            return None

        slug = self._extract_restaurant_slug(merchant)
        restaurant_url = self._extract_restaurant_url(merchant, page_url, merchant_id, slug)
        if not restaurant_url:
            return None

        match = RESTAURANT_PATH_RE.search(restaurant_url)
        if match:
            slug = match.group(2)

        self._seen_restaurant_ids.add(merchant_id)
        return {
            "id": merchant_id,
            "slug": slug,
            "name": self._extract_merchant_name(merchant),
            "latlng": merchant.get("latlng") or fallback_latlng,
            "url": restaurant_url,
        }

    def _find_merchants(self, payload):
        merchants = []

        def walk(node):
            if isinstance(node, dict):
                value = node.get("merchants")
                if isinstance(value, list):
                    merchants.extend(item for item in value if isinstance(item, dict))
                for nested in node.values():
                    walk(nested)
            elif isinstance(node, list):
                for nested in node:
                    walk(nested)

        walk(payload)
        return merchants

    def _extract_merchant_payload(self, payloads, merchant_id):
        for payload in reversed(payloads):
            merchant = payload.get("merchant")
            if not isinstance(merchant, dict):
                continue
            candidate_id = merchant.get("ID") or merchant.get("id")
            if not merchant_id or candidate_id == merchant_id:
                return payload
        return None

    def _parse_merchant_payload(self, payload, restaurant_url):
        merchant = payload.get("merchant") or {}
        outlet_name = merchant.get("name") or "Unknown Outlet"
        categories = ((merchant.get("menu") or {}).get("categories") or [])
        items = []

        for category in categories:
            category_name = category.get("name") or None
            category_available = category.get("available")
            for menu_item in category.get("items") or []:
                item = self._build_menu_item(
                    menu_item,
                    outlet_name,
                    category_name,
                    restaurant_url,
                    category_available,
                )
                if item:
                    items.append(item)
        return items

    def _build_menu_item(
        self,
        menu_item,
        outlet_name,
        category_name,
        restaurant_url,
        category_available=True,
    ):
        name = menu_item.get("name")
        if not name:
            return None

        original_price = self._format_price(menu_item.get("priceV2"))
        discounted_price = self._format_price(menu_item.get("discountedPriceV2"))
        has_promo = bool(discounted_price and discounted_price != original_price)

        available = menu_item.get("available")
        if available is None:
            available = True if category_available is None else category_available

        promo_nominal = None
        if has_promo:
            difference = self._extract_promo_difference(
                menu_item.get("priceV2"),
                menu_item.get("discountedPriceV2"),
            )
            if difference is not None:
                promo_nominal = self._format_currency(difference)

        return {
            "outlet_name": outlet_name,
            "category_name": category_name,
            "menu_name": name,
            "menu_description": menu_item.get("description") or None,
            "original_price": original_price,
            "promo_price": discounted_price if has_promo else None,
            "promo_nominal": promo_nominal,
            "promo_percentage": menu_item.get("discountPercentage") if has_promo else None,
            "availability": "Available" if available else "Sold Out",
            "menu_url": restaurant_url,
        }

    @staticmethod
    def _extract_next_data(response):
        raw_next_data = response.css("#__NEXT_DATA__::text").get()
        if not raw_next_data:
            return {}
        try:
            parsed = json.loads(raw_next_data)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @classmethod
    def _extract_listing_latlng(cls, next_data):
        page_props = ((next_data.get("props") or {}).get("pageProps") or {})
        payload = page_props.get("payload")
        if isinstance(payload, dict):
            latlng = payload.get("latlng")
            if latlng:
                return latlng
        return cls._find_first_string_by_key(next_data, "latlng")

    @classmethod
    def _extract_restaurant_slug(cls, merchant):
        for key in ("slug", "merchantSlug", "seoName", "friendlyName"):
            value = merchant.get(key)
            if value:
                return value

        path = cls._extract_restaurant_path(merchant)
        if path:
            match = RESTAURANT_PATH_RE.search(path)
            if match:
                return match.group(2)

        name = cls._extract_merchant_name(merchant)
        if not name:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
        return slug or None

    @classmethod
    def _extract_restaurant_url(cls, merchant, page_url, merchant_id, slug):
        path = cls._extract_restaurant_path(merchant)
        if path:
            match = RESTAURANT_PATH_RE.search(path)
            if match:
                return urljoin(page_url, match.group(1))
        if slug and merchant_id:
            return "https://food.grab.com/id/id/restaurant/%s/%s" % (slug, merchant_id)
        return None

    @classmethod
    def _extract_restaurant_path(cls, merchant):
        for value in cls._iter_strings(merchant):
            match = RESTAURANT_PATH_RE.search(value)
            if match:
                return match.group(0)
        return None

    @staticmethod
    def _extract_merchant_name(merchant):
        for value in (
            merchant.get("name"),
            (merchant.get("brand") or {}).get("name"),
            (merchant.get("chain") or {}).get("name"),
        ):
            if value:
                return value
        return None

    @classmethod
    def _iter_strings(cls, value):
        if isinstance(value, str):
            yield value
            return
        if isinstance(value, dict):
            for nested in value.values():
                yield from cls._iter_strings(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from cls._iter_strings(nested)

    @classmethod
    def _find_first_string_by_key(cls, value, target_key):
        if isinstance(value, dict):
            if value.get(target_key):
                return value.get(target_key)
            for nested in value.values():
                result = cls._find_first_string_by_key(nested, target_key)
                if result:
                    return result
        elif isinstance(value, list):
            for nested in value:
                result = cls._find_first_string_by_key(nested, target_key)
                if result:
                    return result
        return None

    @staticmethod
    def _format_price(price_obj):
        if not isinstance(price_obj, dict):
            return None
        amount_display = price_obj.get("amountDisplay")
        if amount_display:
            return "Rp%s" % amount_display
        amount_minor = price_obj.get("amountInMinor")
        if isinstance(amount_minor, (int, float)):
            return GrabFoodSpider._format_currency(int(round(amount_minor / 100)))
        return None

    @staticmethod
    def _extract_promo_difference(original_price, discounted_price):
        original_minor = GrabFoodSpider._extract_minor_amount(original_price)
        discounted_minor = GrabFoodSpider._extract_minor_amount(discounted_price)
        if original_minor is not None and discounted_minor is not None and original_minor > discounted_minor:
            return int(round((original_minor - discounted_minor) / 100))

        original_value = GrabFoodSpider._extract_price_value(original_price)
        discounted_value = GrabFoodSpider._extract_price_value(discounted_price)
        if original_value is not None and discounted_value is not None and original_value > discounted_value:
            return original_value - discounted_value
        return None

    @staticmethod
    def _extract_minor_amount(price_obj):
        if isinstance(price_obj, dict) and isinstance(price_obj.get("amountInMinor"), (int, float)):
            return int(price_obj["amountInMinor"])
        return None

    @staticmethod
    def _extract_price_value(price_obj):
        if not isinstance(price_obj, dict):
            return None
        amount_display = price_obj.get("amountDisplay")
        if not amount_display:
            return None
        digits = re.sub(r"[^0-9]", "", str(amount_display))
        if not digits:
            return None
        return int(digits)

    @staticmethod
    def _format_currency(value):
        if value is None:
            return None
        return "Rp%s" % format(int(value), ",").replace(",", ".")

    @staticmethod
    def _parse_limit(limit):
        if limit in (None, "", "None"):
            return None
        try:
            parsed = int(limit)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    async def _extract_outlet_name(self, page, fallback_name=None):
        for selector in ("h1", "[data-testid='restaurant-name']", ".restaurantName"):
            element = await page.query_selector(selector)
            if not element:
                continue
            text = await element.inner_text()
            if text and text.strip():
                return text.strip()
        return fallback_name or "Unknown Outlet"

    async def _scroll_to_load_all(self, page):
        previous_height = -1
        for _ in range(20):
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                break
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)
            previous_height = current_height
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1000)

    async def _extract_dom_menu_data(self, page, outlet_name, restaurant_url):
        try:
            raw_items = await page.evaluate(
                """
                () => {
                    const items = [];
                    document.querySelectorAll(
                        '.menuItem, [data-testid="menu-item"], .itemMainMenu, ' +
                        '[class*="menuItem"], [class*="menu-item"]'
                    ).forEach((el) => {
                        const name = el.querySelector(
                            '.itemNameTitle, [data-testid="item-name"], .item-name, ' +
                            'h3, .itemName, [class*="itemName"]'
                        );
                        if (!name) return;
                        const description = el.querySelector(
                            '.itemDescription, .item-desc, p, [class*="description"]'
                        );
                        const originalPrice = el.querySelector(
                            '.originPrice, .originalPrice, [class*="originalPrice"], ' +
                            '[class*="originPrice"]'
                        );
                        const promoPrice = el.querySelector(
                            '.discountedPrice, .promoPrice, .salePrice, ' +
                            '[class*="discountedPrice"], [class*="promoPrice"]'
                        );
                        const soldOut = el.querySelector(
                            '.disableOverlay, .soldOutOverlay, .unavailable, ' +
                            '[class*="soldOut"], [class*="disable"]'
                        );
                        items.push({
                            menu_name: name.textContent.trim(),
                            menu_description: description ? description.textContent.trim() : null,
                            original_price: originalPrice ? originalPrice.textContent.trim() : null,
                            promo_price: promoPrice ? promoPrice.textContent.trim() : null,
                            availability: soldOut ? 'Sold Out' : 'Available',
                        });
                    });
                    return items;
                }
                """
            )
        except Exception:
            logger.warning("DOM extraction failed for %s", restaurant_url, exc_info=True)
            return []

        items = []
        for raw_item in raw_items or []:
            original_price = raw_item.get("original_price")
            promo_price = raw_item.get("promo_price")
            if promo_price == original_price:
                promo_price = None
            items.append(
                {
                    "outlet_name": outlet_name,
                    "category_name": None,
                    "menu_name": raw_item.get("menu_name"),
                    "menu_description": raw_item.get("menu_description"),
                    "original_price": original_price,
                    "promo_price": promo_price,
                    "promo_nominal": None,
                    "promo_percentage": None,
                    "availability": raw_item.get("availability") or "Available",
                    "menu_url": restaurant_url,
                }
            )
        return items

    async def errback_close_page(self, failure):
        page = failure.request.meta.get("playwright_page")
        if page:
            await page.close()
        logger.error("Request failed for %s: %s", failure.request.url, failure.value)
