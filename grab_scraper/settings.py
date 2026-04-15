BOT_NAME = "grab_scraper"
SPIDER_MODULES = ["grab_scraper.spiders"]
NEWSPIDER_MODULE = "grab_scraper.spiders"

ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS = 2
CONCURRENT_REQUESTS_PER_DOMAIN = 2

DOWNLOAD_DELAY = 3
RANDOMIZE_DOWNLOAD_DELAY = True

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 3
AUTOTHROTTLE_MAX_DELAY = 15
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = False

RETRY_ENABLED = True
RETRY_TIMES = 5
RETRY_HTTP_CODES = [429, 500, 502, 503, 504, 408]
RETRY_PRIORITY_ADJUST = -1

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
}

COOKIES_ENABLED = True
COOKIES_DEBUG = False

DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": None,
    "grab_scraper.middlewares.UserAgentRotationMiddleware": 400,
    "grab_scraper.middlewares.ExponentialBackoffRetryMiddleware": 550,
    "grab_scraper.middlewares.AntiDetectionMiddleware": 700,
}

ITEM_PIPELINES = {
    "grab_scraper.pipelines.ValidationPipeline": 100,
    "grab_scraper.pipelines.DataCleaningPipeline": 200,
    "grab_scraper.pipelines.DuplicateFilterPipeline": 300,
}

FEEDS = {
    "output/%(name)s_%(time)s.csv": {
        "format": "csv",
        "encoding": "utf-8",
        "overwrite": True,
        "fields": [
            "outlet_name", "category_name", "menu_name", "menu_description",
            "original_price", "promo_price", "promo_nominal",
            "promo_percentage", "availability", "menu_url",
            "merchant_id", "item_id", "image_url", "dietary_tags",
            "is_top_seller", "takeaway_price", "promo_takeaway_price",
            "cuisine", "rating", "vote_count",
            "distance_km", "estimated_delivery_time", "latitude",
            "longitude", "chain_name", "branch_name", "price_tag",
            "is_open", "delivery_fee", "merchant_photo",
            "delivery_options", "business_type",
            "service_fee", "merchant_cuisine", "merchant_rating",
            "merchant_vote_count", "eta_minutes", "is_integrated",
            "merchant_status",
        ],
    },
    "output/%(name)s_%(time)s.json": {
        "format": "json",
        "encoding": "utf-8",
        "overwrite": True,
        "indent": 2,
    },
}

LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

DOWNLOAD_TIMEOUT = 120
