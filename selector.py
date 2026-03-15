"""Gemini AI를 사용하여 여행 사진/영상을 선별하는 모듈."""

import json
import base64
from pathlib import Path
from google import genai
from PIL import Image
import io

import config


def _load_image_as_base64(file_path: str, max_size: int = 1024) -> str:
    """이미지를 리사이징하고 base64로 인코딩."""
    img = Image.open(file_path)
    img.thumbnail((max_size, max_size))

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")


def select_best_photos(
    location_groups: list[dict],
    max_per_group: int = 5,
    max_total: int = 30,
    api_key: str = None,
) -> list[dict]:
    """각 장소 그룹에서 Gemini AI로 베스트 사진을 선별한다.

    Args:
        location_groups: group_by_location() 결과
        max_per_group: 그룹당 최대 선택 수
        max_total: 전체 최대 선택 수
        api_key: Gemini API 키 (없으면 config에서 로드)

    Returns:
        선별된 미디어 정보 리스트 (순서 유지)
    """
    key = api_key or config.GEMINI_API_KEY
    client = genai.Client(api_key=key)
    selected_all = []

    for group in location_groups:
        images = [f for f in group["files"] if f["type"] == "image"]
        videos = [f for f in group["files"] if f["type"] == "video"]

        # 영상은 무조건 포함
        selected_all.extend(videos)

        if not images:
            continue

        if len(images) <= max_per_group:
            selected_all.extend(images)
            continue

        # Gemini에게 사진 품질 평가 요청
        print(f"[selector] '{group['location_name']}' - {len(images)}장 중 베스트 {max_per_group}장 선별 중...")

        parts = []
        file_index_map = {}

        for i, img_file in enumerate(images):
            try:
                b64 = _load_image_as_base64(img_file["path"])
                parts.append(genai.types.Part.from_bytes(
                    data=base64.standard_b64decode(b64),
                    mime_type="image/jpeg",
                ))
                parts.append(genai.types.Part.from_text(text=f"[사진 {i}] {img_file['filename']}"))
                file_index_map[i] = img_file
            except Exception as e:
                print(f"  [!] {img_file['filename']} 로드 실패: {e}")

        prompt = f"""당신은 여행 영상 편집 전문가입니다.
위 사진들은 '{group['location_name']}'에서 찍은 여행 사진입니다.

이 중에서 여행 유튜브 영상에 넣기 가장 좋은 사진 {max_per_group}장을 골라주세요.

선택 기준:
- 구도와 색감이 좋은 사진
- 여행 분위기가 잘 드러나는 사진
- 랜드마크나 특색있는 장소가 보이는 사진
- 흐릿하거나 어두운 사진은 제외

반드시 아래 JSON 형식으로만 응답하세요:
{{"selected": [0, 3, 5]}}

selected에는 선택한 사진의 번호(0부터 시작)를 넣어주세요."""

        parts.append(genai.types.Part.from_text(text=prompt))

        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=genai.types.Content(parts=parts),
            )

            text = response.text.strip()
            # JSON 파싱 (코드블록 제거)
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text)
            indices = result.get("selected", [])

            for idx in indices:
                if idx in file_index_map:
                    selected_all.append(file_index_map[idx])

            print(f"  → {len(indices)}장 선택됨")

        except Exception as e:
            print(f"  [!] Gemini 선별 실패, 최신 {max_per_group}장 사용: {e}")
            selected_all.extend(images[:max_per_group])

    # 전체 개수 제한
    if len(selected_all) > max_total:
        selected_all = selected_all[:max_total]

    print(f"[selector] 총 {len(selected_all)}개 미디어 선별 완료")
    return selected_all
