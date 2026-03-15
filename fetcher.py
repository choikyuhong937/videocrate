"""로컬 폴더에서 이미지/영상 파일을 로드하는 모듈."""

import os
from pathlib import Path
from datetime import datetime

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}
ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def scan_local_folder(folder_path: str, date_from: str = None, date_to: str = None) -> list[dict]:
    """로컬 폴더에서 미디어 파일을 스캔하고 기본 정보를 반환한다.

    Args:
        folder_path: 스캔할 폴더 경로
        date_from: 시작 날짜 필터 (YYYY-MM-DD)
        date_to: 종료 날짜 필터 (YYYY-MM-DD)

    Returns:
        [{path, filename, type, modified_time}] 리스트
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise FileNotFoundError(f"폴더를 찾을 수 없습니다: {folder_path}")

    from_dt = datetime.strptime(date_from, "%Y-%m-%d") if date_from else None
    to_dt = datetime.strptime(date_to, "%Y-%m-%d") if date_to else None

    media_files = []

    for file_path in sorted(folder.rglob("*")):
        if not file_path.is_file():
            continue

        ext = file_path.suffix.lower()
        if ext not in ALL_EXTENSIONS:
            continue

        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

        if from_dt and mtime < from_dt:
            continue
        if to_dt and mtime > to_dt:
            continue

        media_type = "image" if ext in IMAGE_EXTENSIONS else "video"

        media_files.append({
            "path": str(file_path),
            "filename": file_path.name,
            "type": media_type,
            "modified_time": mtime.isoformat(),
        })

    print(f"[fetcher] {len(media_files)}개 미디어 파일 발견 (이미지: {sum(1 for m in media_files if m['type'] == 'image')}, 영상: {sum(1 for m in media_files if m['type'] == 'video')})")
    return media_files
