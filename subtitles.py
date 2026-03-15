"""Gemini AI를 사용하여 여행 자막을 생성하고 SRT 파일로 출력하는 모듈."""

import json
import base64
import io
from pathlib import Path
from google import genai
from PIL import Image

import config


def _load_image_as_base64(file_path: str, max_size: int = 768) -> str:
    """이미지를 리사이징하고 base64로 인코딩."""
    img = Image.open(file_path)
    img.thumbnail((max_size, max_size))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=80)
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")


def generate_subtitles(
    selected_media: list[dict],
    location_groups: list[dict],
    photo_duration: int = 4,
    lang: str = "ko",
    api_key: str = None,
) -> list[dict]:
    """선별된 미디어에 대해 Gemini로 자막을 생성한다.

    - 장소 전환 시: 정보형 타이틀 (장소명, 날짜)
    - 각 장면: 감성 여행 자막

    Returns:
        [{start_time, end_time, text, style}] 자막 리스트
    """
    key = api_key or config.GEMINI_API_KEY
    client = genai.Client(api_key=key)

    # 선별된 미디어가 어떤 그룹에 속하는지 매핑
    file_to_group = {}
    for group in location_groups:
        for f in group["files"]:
            file_to_group[f["path"]] = group

    subtitles = []
    current_time = 0.0
    current_location = None

    # 이미지들을 배치로 모아서 한번에 Gemini에 보내기
    image_batch = []
    batch_indices = []

    for i, media in enumerate(selected_media):
        group = file_to_group.get(media["path"])
        location_name = group["location_name"] if group else "알 수 없는 장소"
        date_range = group.get("date_range", "") if group else ""

        # 장소 전환 감지 → 정보형 타이틀 자막
        if location_name != current_location:
            current_location = location_name
            title_text = location_name
            if date_range:
                title_text += f"\n{date_range}"

            subtitles.append({
                "index": len(subtitles) + 1,
                "start_time": current_time,
                "end_time": current_time + 3.0,
                "text": title_text,
                "style": "title",
            })

        if media["type"] == "image":
            image_batch.append(media)
            batch_indices.append((i, current_time))
            current_time += photo_duration
        else:
            current_time += photo_duration  # 영상도 기본 duration 적용

    # Gemini로 감성 자막 일괄 생성
    if image_batch:
        print(f"[subtitles] {len(image_batch)}장에 대한 감성 자막 생성 중...")

        # 배치 크기 제한 (한번에 최대 10장)
        batch_size = 10
        caption_results = []

        for batch_start in range(0, len(image_batch), batch_size):
            batch = image_batch[batch_start:batch_start + batch_size]
            parts = []

            for j, media in enumerate(batch):
                try:
                    b64 = _load_image_as_base64(media["path"])
                    parts.append(genai.types.Part.from_bytes(
                        data=base64.standard_b64decode(b64),
                        mime_type="image/jpeg",
                    ))
                    parts.append(genai.types.Part.from_text(text=f"[사진 {batch_start + j}]"))
                except Exception as e:
                    print(f"  [!] {media['filename']} 로드 실패: {e}")
                    parts.append(genai.types.Part.from_text(text=f"[사진 {batch_start + j}] (로드 실패)"))

            lang_name = "한국어" if lang == "ko" else "English"
            prompt = f"""당신은 감성적인 여행 유튜브 영상의 자막 작가입니다.

위 여행 사진들을 보고, 각 사진에 어울리는 짧은 감성 자막을 {lang_name}로 만들어주세요.

규칙:
- 각 자막은 1-2줄, 최대 30자 이내
- 여행의 감성과 분위기를 담은 서정적인 문체
- 사진에 보이는 장면을 묘사하되, 감정도 담기
- 예시: "골목길 끝에서 만난 작은 행복", "바다가 노을에 물드는 시간"

반드시 아래 JSON 형식으로만 응답하세요:
{{"captions": ["자막1", "자막2", ...]}}

사진 순서대로 자막을 만들어주세요."""

            parts.append(genai.types.Part.from_text(text=prompt))

            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=genai.types.Content(parts=parts),
                )
                text = response.text.strip()
                if "```" in text:
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                result = json.loads(text)
                caption_results.extend(result.get("captions", []))
            except Exception as e:
                print(f"  [!] 자막 생성 실패: {e}")
                caption_results.extend([""] * len(batch))

        # 감성 자막을 시간축에 배치
        for j, (media_idx, start_time) in enumerate(batch_indices):
            caption = caption_results[j] if j < len(caption_results) else ""
            if caption:
                subtitles.append({
                    "index": len(subtitles) + 1,
                    "start_time": start_time + 0.5,
                    "end_time": start_time + photo_duration - 0.5,
                    "text": caption,
                    "style": "caption",
                })

    # 시간순 정렬
    subtitles.sort(key=lambda s: s["start_time"])
    for i, sub in enumerate(subtitles):
        sub["index"] = i + 1

    print(f"[subtitles] 총 {len(subtitles)}개 자막 생성 완료")
    return subtitles


def _format_srt_time(seconds: float) -> str:
    """초를 SRT 시간 형식(HH:MM:SS,mmm)으로 변환."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(subtitles: list[dict], output_path: str):
    """자막 리스트를 SRT 파일로 저장."""
    with open(output_path, "w", encoding="utf-8") as f:
        for sub in subtitles:
            f.write(f"{sub['index']}\n")
            f.write(f"{_format_srt_time(sub['start_time'])} --> {_format_srt_time(sub['end_time'])}\n")
            f.write(f"{sub['text']}\n\n")

    print(f"[subtitles] SRT 파일 저장: {output_path}")
