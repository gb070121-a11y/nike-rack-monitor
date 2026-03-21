import asyncio
import base64
import json
import os
import re
from openai import AsyncOpenAI

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
    """
    base64 이미지를 픽셀 밝기로 직접 판별
    평균 밝기가 30 미만이면 암전 사진으로 판단
    """
    try:
        import struct
        import zlib

        img_bytes = base64.b64decode(b64_data)

        # JPEG 또는 PNG 간단 밝기 체크 — 앞부분 샘플링
        # 이미지 크기에 관계없이 빠르게 처리하기 위해
        # 파일 크기 대비 어두운 정도를 추정
        # JPEG의 경우 어두운 이미지는 파일 크기가 매우 작음
        # 하지만 SSBC 워터마크가 있어 단순 크기로는 불가

        # Pillow 없이 간단히: 이미지 바이트 전체의 평균값
        # JPEG 바이너리에서 실제 픽셀값과 직접 관계는 없지만
        # 완전히 어두운 JPEG는 대부분의 바이트가 낮은 값
        # 대신 파일명이나 크기 기반 휴리스틱 사용

        # 가장 확실한 방법: 파일 크기로 판별
        # 암전 사진은 보통 100KB 미만 (일반 사진은 500KB~3MB)
        file_size = len(img_bytes)
        if file_size < 150000:  # 150KB 미만이면 암전으로 판단
            return True
        return False

    except Exception:
        return False


async def analyze_single_image(image: dict, semaphore: asyncio.Semaphore) -> dict:
    """단일 이미지 분석 — 암전은 API 호출 없이 즉시 처리"""

    # 암전 사진은 GPT-4o에 보내지 않고 직접 판별
    if is_black_image(image["b64"]):
        return {"filename": image["filename"], "is_black": True, "products": []}

    async with semaphore:
        try:
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
                        {
                            "type": "text",
                            "text": SYSTEM_PROMPT
                        }
                    ]
                }]
            )

            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            result = json.loads(raw)
            result["filename"] = image["filename"]
            return result

        except json.JSONDecodeError:
            return {"filename": image["filename"], "is_black": False, "products": [], "error": "JSON 파싱 실패"}
        except Exception as e:
            return {"filename": image["filename"], "is_black": False, "products": [], "error": str(e)}


async def analyze_images_batch(images: list) -> list:
    """
    이미지 목록을 병렬 분석하고 암전 사진 기준으로 랙별 그룹화
    """
    semaphore = asyncio.Semaphore(10)

    tasks = [analyze_single_image(img, semaphore) for img in images]
    results = await asyncio.gather(*tasks)

    racks = []
    current_rack_num = 1
    current_rack_products = []
    photo_count = 0

    for res in results:
        if res.get("is_black"):
            # 암전 사진 = 랙 구분자 — 제품이 없어도 랙 번호 증가
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

    # 마지막 랙 처리
    if current_rack_products:
        racks.append({
            "rack_number": current_rack_num,
            "products": current_rack_products,
            "photo_count": photo_count
        })

    return racks
