import asyncio
import base64
import json
import os
import re
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

SYSTEM_PROMPT = """당신은 나이키 매장 신발 진열 랙 사진을 분석하는 전문가입니다.
사진에서 신발 태그나 가격표를 보고 다음을 JSON으로 정확하게 추출하세요:

{
  "is_black": false,         // 검은 암전 사진이면 true (랙 구분자)
  "products": [
    {
      "sku": "품번(예: DV4305-100)",
      "name": "제품명(보이면)",
      "price": 129000,       // 정가 숫자만
      "sale_price": 89000,   // 할인가 숫자만, 없으면 null
      "discount_rate": 31,   // 할인율 % 숫자만, 없으면 null
      "position": 1          // 사진에서 왼쪽부터 순서
    }
  ]
}

규칙:
- 검은 화면이거나 완전히 어두운 사진이면 is_black: true, products: []
- 가격은 숫자만 (원 기호, 쉼표 제거)
- 품번이 안 보이면 "UNKNOWN_N" 형식
- JSON만 출력, 다른 텍스트 없음"""


async def analyze_single_image(image: dict, semaphore: asyncio.Semaphore) -> dict:
    """단일 이미지 분석 (세마포어로 동시 요청 제한)"""
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
            # 코드블록 제거
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
    이미지 목록을 병렬 분석하고 검은 암전 사진 기준으로 랙별로 그룹화
    동시 요청은 최대 10개로 제한 (API 레이트 리밋 대응)
    """
    semaphore = asyncio.Semaphore(10)

    # 병렬 분석
    tasks = [analyze_single_image(img, semaphore) for img in images]
    results = await asyncio.gather(*tasks)

    # 랙별 그룹화
    racks = []
    current_rack_num = 1
    current_rack_products = []
    photo_count = 0

    for res in results:
        if res.get("is_black"):
            # 암전 사진 = 랙 구분자
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
