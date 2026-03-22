import asyncio
import base64
import json
import os
import re
import logging
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

SYSTEM_PROMPT = """You are an expert at reading Nike store shelf photos taken in Korean outlet stores.

PHOTO LAYOUTS — there are two common layouts, handle both:

LAYOUT A (most common):
- Upper area: Price display slot showing 3 lines (original price / X% OFF / sale price)
- Lower area: Nike shoe box with a small label containing the SKU

LAYOUT B (also common):
- Upper area: Nike shoe box label visible ABOVE the price slot
- Lower area: Price display slot
- OR: Box label appears beside or overlapping the price tag area

IN BOTH CASES — look for ALL of these anywhere in the photo:
1. PRICE INFO: Three numbers in a slot/frame — largest number = original price, "X% OFF" = discount, last number = sale price
2. SKU/ARTICLE NUMBER: Alphanumeric code on box label sticker

SKU format examples: FQ8325 300, FN0697 100, HV9305 300, IM5676 003, FV4898 400, HQ2159 100, HQ2158 001
- Pattern: 2 letters + 4 digits + space + 3 digits
- On white or orange/red sticker label on the shoe box
- Product names also on label: "AIR MAX 90 G", "VICTORY PRO 4 W", "INFINITY TOUR NEXT% 2 GTX W" etc.

Return ONLY valid JSON:
{
  "is_black": false,
  "products": [
    {
      "sku": "FQ8325 300",
      "name": "AIR MAX 90 G",
      "price": 189000,
      "sale_price": 113400,
      "discount_rate": 40,
      "position": 1
    }
  ]
}

Rules:
- price = original price digits only (no commas, no currency symbol)
- sale_price = final discounted price digits only
- discount_rate = percentage number only (e.g. 40 for "40% OFF")
- sku = search the ENTIRE image carefully. Even if small, tilted, or partially visible — try hard to read it.
- name = product name from box label if visible
- If SKU truly cannot be read: "UNKNOWN"
- JSON only, no markdown, no explanation"""


def is_black_image(b64_data: str) -> bool:
    try:
        img_bytes = base64.b64decode(b64_data)
        file_size = len(img_bytes)
        if file_size < 300000:
            return True
        return False
    except Exception:
        return False


async def analyze_single_image(image: dict, semaphore: asyncio.Semaphore) -> dict:
    if is_black_image(image["b64"]):
        logger.info(f"Black image detected: {image['filename']}")
        return {"filename": image["filename"], "is_black": True, "products": []}

    async with semaphore:
        try:
            logger.info(f"Analyzing: {image['filename']}")
            response = await client.chat.completions.create(
                model="gpt-4o",
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image['content_type']};base64,{image['b64']}",
                                "detail": "high"
                            }
                        },
                        {"type": "text", "text": SYSTEM_PROMPT}
                    ]
                }]
            )
            raw = response.choices[0].message.content.strip()
            logger.info(f"GPT response for {image['filename']}: {raw[:200]}")
            raw = re.sub(r"```json|```", "", raw).strip()
            result = json.loads(raw)
            result["filename"] = image["filename"]
            logger.info(f"Parsed {len(result.get('products',[]))} products from {image['filename']}")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for {image['filename']}: {e}")
            return {"filename": image["filename"], "is_black": False, "products": [], "error": "JSON 파싱 실패"}
        except Exception as e:
            logger.error(f"Error analyzing {image['filename']}: {str(e)}")
            return {"filename": image["filename"], "is_black": False, "products": [], "error": str(e)}


async def analyze_images_batch(images: list, start_rack_num: int = 1, single_rack: bool = False) -> list:
    logger.info(f"Starting batch analysis: {len(images)} images, start_rack={start_rack_num}")
    semaphore = asyncio.Semaphore(10)
    tasks = [analyze_single_image(img, semaphore) for img in images]
    results = await asyncio.gather(*tasks)

    racks = []
    current_rack_num = start_rack_num
    current_rack_products = []
    photo_count = 0

    for res in results:
        if res.get("is_black"):
            if single_rack:
                continue
            if current_rack_products:
                racks.append({
                    "rack_number": current_rack_num,
                    "products": current_rack_products,
                    "photo_count": photo_count
                })
            current_rack_num += 1
            current_rack_products = []
            photo_count = 0
        else:
            photo_count += 1
            products = res.get("products", [])
            for p in products:
                p["photo_file"] = res.get("filename", "")
            current_rack_products.extend(products)

    if current_rack_products:
        racks.append({
            "rack_number": current_rack_num,
            "products": current_rack_products,
            "photo_count": photo_count
        })

    logger.info(f"Batch complete: {len(racks)} racks, {sum(len(r['products']) for r in racks)} products")
    return racks
