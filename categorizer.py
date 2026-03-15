"""Gemini AI를 사용하여 사진을 스마트 테마 카드로 자동 분류하는 모듈.

테마 유형: 여행(travel), 아기성장(baby), 이벤트(event), 계절(seasonal), 일상(daily)
전략: 메타데이터 매니페스트(텍스트) + 샘플 이미지(시각)를 Gemini에 전달하여 분류.
"""

import json
import base64

from google import genai

import config
from selector import _load_image_as_base64


THEME_TYPE_LABELS = {
    "travel": "여행",
    "baby": "아기",
    "event": "이벤트",
    "seasonal": "계절",
    "daily": "일상",
}


def _build_manifest(media_files):
    """사진 메타데이터를 텍스트 매니페스트로 정리."""
    lines = []
    for i, f in enumerate(media_files):
        loc = f.get("location_name", "")
        lat = f.get("lat")
        lon = f.get("lon")
        gps_str = f"{lat:.4f}/{lon:.4f}" if lat and lon else "없음"
        dt = f.get("datetime", f.get("modified_time", ""))
        ftype = f.get("type", "image")
        lines.append(
            f"[{i}] {f['filename']}  날짜={dt}  위치={loc}  GPS={gps_str}  유형={ftype}"
        )
    return "\n".join(lines)


def _select_sample_images(media_files, location_groups, max_samples=20):
    """각 위치 그룹에서 대표 이미지를 선택하여 샘플로 추출."""
    samples = []  # [(global_index, file_path)]
    images_only = [
        (i, f) for i, f in enumerate(media_files) if f["type"] == "image"
    ]

    if not images_only:
        return samples

    if location_groups:
        # 각 그룹에서 첫 번째 + 중간 이미지 선택
        per_group = max(1, max_samples // max(len(location_groups), 1))
        for group in location_groups:
            group_images = [f for f in group["files"] if f["type"] == "image"]
            if not group_images:
                continue

            # 첫 번째 이미지
            first = group_images[0]
            idx = next(
                (i for i, f in enumerate(media_files) if f["path"] == first["path"]),
                None,
            )
            if idx is not None:
                samples.append((idx, first["path"]))

            # 중간 이미지 (다르면)
            if len(group_images) > 2 and per_group > 1:
                mid = group_images[len(group_images) // 2]
                idx2 = next(
                    (i for i, f in enumerate(media_files) if f["path"] == mid["path"]),
                    None,
                )
                if idx2 is not None and idx2 != idx:
                    samples.append((idx2, mid["path"]))

            if len(samples) >= max_samples:
                break
    else:
        # 그룹이 없으면 균등 간격으로 샘플링
        step = max(1, len(images_only) // max_samples)
        for j in range(0, len(images_only), step):
            i, f = images_only[j]
            samples.append((i, f["path"]))
            if len(samples) >= max_samples:
                break

    return samples[:max_samples]


def _fallback_from_location_groups(media_files, location_groups):
    """Gemini 실패시 기존 위치 그룹을 테마 카드 형식으로 변환."""
    cards = []
    for i, group in enumerate(location_groups):
        image_files = [f for f in group["files"] if f["type"] == "image"]
        video_files = [f for f in group["files"] if f["type"] == "video"]
        thumbnail = image_files[0]["filename"] if image_files else None

        cards.append({
            "id": i,
            "name": group["location_name"],
            "type": "travel",
            "emoji": "\U0001f4cd",  # 📍
            "description": "",
            "date_range": group.get("date_range", ""),
            "files": group["files"],
            "photo_count": len(image_files),
            "video_count": len(video_files),
            "thumbnail": thumbnail,
        })
    return cards


def categorize_photos(media_files, location_groups, api_key=None):
    """사진 컬렉션을 Gemini AI로 분석하여 테마 카드로 분류.

    Args:
        media_files: enrich_media_with_metadata() 결과
        location_groups: group_by_location() 결과
        api_key: Gemini API 키 (없으면 config에서 로드)

    Returns:
        테마 카드 리스트 [{id, name, type, emoji, description, date_range,
                          files, photo_count, video_count, thumbnail}]
    """
    key = api_key or config.GEMINI_API_KEY
    if not key:
        print("[categorizer] API 키 없음 - 위치 기반 분류로 대체")
        return _fallback_from_location_groups(media_files, location_groups)

    if not media_files:
        return []

    try:
        client = genai.Client(api_key=key)
        return _run_categorization(client, media_files, location_groups)
    except Exception as e:
        print(f"[categorizer] AI 분류 실패, 위치 기반 fallback: {e}")
        return _fallback_from_location_groups(media_files, location_groups)


def _run_categorization(client, media_files, location_groups):
    """Gemini API를 호출하여 테마 분류 수행."""
    # 매니페스트 생성
    manifest = _build_manifest(media_files)

    # 샘플 이미지 선택
    samples = _select_sample_images(media_files, location_groups, max_samples=20)

    # Gemini 요청 구성
    parts = []

    # 샘플 이미지 추가
    for global_idx, file_path in samples:
        try:
            b64 = _load_image_as_base64(file_path, max_size=512)
            parts.append(genai.types.Part.from_bytes(
                data=base64.standard_b64decode(b64),
                mime_type="image/jpeg",
            ))
            parts.append(genai.types.Part.from_text(
                text=f"[사진 {global_idx}]"
            ))
        except Exception as e:
            print(f"[categorizer] 샘플 이미지 로드 실패: {file_path} - {e}")

    # 프롬프트
    prompt = f"""당신은 사진 분류 AI 전문가입니다. 아래는 사용자의 사진 컬렉션입니다.

## 사진 메타데이터 목록 (총 {len(media_files)}장)
{manifest}

## 위의 샘플 이미지들을 참고하여 분석해주세요.

모든 사진을 의미있는 "테마 카드"로 분류해주세요.

### 테마 카드 유형:
1. **여행 (travel)**: 같은 여행지의 사진들. 예: "제주도 여행", "도쿄 3박4일"
2. **아기 성장 (baby)**: 아기/유아 사진이 있으면 월령·시기별로. 예: "우리 아기 100일", "아기 첫 걸음마"
3. **이벤트 (event)**: 파티, 생일, 졸업식, 크리스마스 등. 예: "크리스마스 2024", "졸업식"
4. **계절/시기 (seasonal)**: 특정 계절이나 시기. 예: "2024 봄", "여름 바다"
5. **일상 (daily)**: 위에 해당하지 않는 일반 사진. 예: "집에서의 하루"

### 규칙:
- 한 사진은 하나의 테마에만 속해야 합니다
- 각 테마에 최소 3장 이상 포함되어야 합니다 (3장 미만이면 다른 테마에 합치세요)
- 테마 이름은 한국어로, 감성적이고 자연스럽게
- 날짜 범위가 있으면 포함하세요
- 적절한 이모지를 선택해주세요

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "themes": [
    {{
      "name": "제주도 여행",
      "type": "travel",
      "description": "서귀포 해안가와 한라산 일대",
      "date_range": "3.15~3.18",
      "emoji": "🏝️",
      "photo_indices": [0, 1, 2, 3, 4, 5]
    }}
  ]
}}

photo_indices에는 위 메타데이터 목록의 번호([0], [1], ...)를 넣어주세요."""

    parts.append(genai.types.Part.from_text(text=prompt))

    # API 호출
    print(f"[categorizer] Gemini에 {len(media_files)}장 분류 요청 (샘플 {len(samples)}장)...")

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=genai.types.Content(parts=parts),
    )

    # JSON 파싱
    text = response.text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    result = json.loads(text)
    themes = result.get("themes", [])

    if not themes:
        print("[categorizer] AI가 테마를 반환하지 않음 - fallback")
        return _fallback_from_location_groups(media_files, location_groups)

    # 테마 카드 구성
    cards = []
    for i, theme in enumerate(themes):
        indices = theme.get("photo_indices", [])
        # 유효한 인덱스만 필터링
        valid_indices = [idx for idx in indices if 0 <= idx < len(media_files)]
        if not valid_indices:
            continue

        files = [media_files[idx] for idx in valid_indices]
        image_files = [f for f in files if f["type"] == "image"]
        video_files = [f for f in files if f["type"] == "video"]
        thumbnail = image_files[0]["filename"] if image_files else None

        cards.append({
            "id": i,
            "name": theme.get("name", f"테마 {i+1}"),
            "type": theme.get("type", "daily"),
            "emoji": theme.get("emoji", "\U0001f4f7"),  # 📷
            "description": theme.get("description", ""),
            "date_range": theme.get("date_range", ""),
            "files": files,
            "photo_count": len(image_files),
            "video_count": len(video_files),
            "thumbnail": thumbnail,
        })

    print(f"[categorizer] {len(cards)}개 테마 카드 생성 완료")
    return cards
