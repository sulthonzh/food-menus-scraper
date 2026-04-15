import scrapy
from itemloaders.processors import TakeFirst, MapCompose


def clean_text(value):
    if not value or not value.strip():
        return None
    return value.strip()


def clean_price(value):
    if not value:
        return None
    return value.strip()


def normalize_availability(value):
    if not value:
        return "Available"
    val = str(value).strip().lower()
    if "sold out" in val or "unavailable" in val or "habis" in val:
        return "Sold Out"
    return "Available"


class GrabMenuItem(scrapy.Item):

    outlet_name = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst(),
    )
    category_name = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst(),
    )
    menu_name = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst(),
    )
    menu_description = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst(),
    )
    original_price = scrapy.Field(
        input_processor=MapCompose(clean_price),
        output_processor=TakeFirst(),
    )
    promo_price = scrapy.Field(
        input_processor=MapCompose(clean_price),
        output_processor=TakeFirst(),
    )
    promo_nominal = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst(),
    )
    promo_percentage = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst(),
    )
    availability = scrapy.Field(
        input_processor=MapCompose(normalize_availability),
        output_processor=TakeFirst(),
    )
    menu_url = scrapy.Field(
        output_processor=TakeFirst(),
    )
    merchant_id = scrapy.Field(
        output_processor=TakeFirst(),
    )
    cuisine = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst(),
    )
    rating = scrapy.Field(
        output_processor=TakeFirst(),
    )
    vote_count = scrapy.Field(
        output_processor=TakeFirst(),
    )
    distance_km = scrapy.Field(
        output_processor=TakeFirst(),
    )
    estimated_delivery_time = scrapy.Field(
        output_processor=TakeFirst(),
    )
    latitude = scrapy.Field(
        output_processor=TakeFirst(),
    )
    longitude = scrapy.Field(
        output_processor=TakeFirst(),
    )
    chain_name = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst(),
    )
    branch_name = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst(),
    )
    price_tag = scrapy.Field(
        output_processor=TakeFirst(),
    )
    is_open = scrapy.Field(
        output_processor=TakeFirst(),
    )
    delivery_fee = scrapy.Field(
        input_processor=MapCompose(clean_price),
        output_processor=TakeFirst(),
    )
    merchant_photo = scrapy.Field(
        output_processor=TakeFirst(),
    )
    delivery_options = scrapy.Field(
        output_processor=TakeFirst(),
    )
    business_type = scrapy.Field(
        output_processor=TakeFirst(),
    )
    item_id = scrapy.Field(
        output_processor=TakeFirst(),
    )
    image_url = scrapy.Field(
        output_processor=TakeFirst(),
    )
    dietary_tags = scrapy.Field(
        output_processor=TakeFirst(),
    )
    is_top_seller = scrapy.Field(
        output_processor=TakeFirst(),
    )
    takeaway_price = scrapy.Field(
        input_processor=MapCompose(clean_price),
        output_processor=TakeFirst(),
    )
    promo_takeaway_price = scrapy.Field(
        input_processor=MapCompose(clean_price),
        output_processor=TakeFirst(),
    )
    service_fee = scrapy.Field(
        input_processor=MapCompose(clean_price),
        output_processor=TakeFirst(),
    )
    merchant_cuisine = scrapy.Field(
        input_processor=MapCompose(clean_text),
        output_processor=TakeFirst(),
    )
    merchant_rating = scrapy.Field(
        output_processor=TakeFirst(),
    )
    merchant_vote_count = scrapy.Field(
        output_processor=TakeFirst(),
    )
    eta_minutes = scrapy.Field(
        output_processor=TakeFirst(),
    )
    is_integrated = scrapy.Field(
        output_processor=TakeFirst(),
    )
    merchant_status = scrapy.Field(
        output_processor=TakeFirst(),
    )
