"""Google OAuth 2.0 + Drive API 연동 모듈.

흐름: OAuth 로그인 → Drive API로 날짜 기반 사진 조회 → 다운로드
(Photos Library API는 2025-03-31 폐지 → Drive API로 대체)
"""

import os
import requests
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def get_auth_url(client_id, redirect_uri, state=""):
    """Google OAuth 인증 URL 생성."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(code, client_id, client_secret, redirect_uri):
    """인증 코드 → 액세스 토큰 교환."""
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def refresh_access_token(refresh_token, client_id, client_secret):
    """리프레시 토큰으로 액세스 토큰 갱신."""
    resp = requests.post(GOOGLE_TOKEN_URL, data={
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_user_info(access_token):
    """로그인된 사용자 정보 조회."""
    resp = requests.get(GOOGLE_USERINFO_URL, headers={
        "Authorization": f"Bearer {access_token}"
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ─── Drive API: 날짜 기반 사진 조회 ───

def list_photos_by_date(access_token, date_from, date_to, max_items=500):
    """Google Drive에서 날짜 범위로 사진/영상을 조회 (메타데이터만, 다운로드 없음).

    Returns:
        Drive 파일 목록 [{id, name, mimeType, createdTime, imageMediaMetadata, thumbnailLink, ...}]
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    fields = "nextPageToken,files(id,name,mimeType,createdTime,modifiedTime,imageMediaMetadata,size,thumbnailLink)"

    all_items = []

    # 이미지와 영상을 각각 조회 (or 조건 대신 분리하여 안정적)
    for mime_filter in ["mimeType contains 'image/'", "mimeType contains 'video/'"]:
        query = f"{mime_filter} and modifiedTime >= '{date_from}T00:00:00' and modifiedTime <= '{date_to}T23:59:59' and trashed = false"
        page_token = None

        while len(all_items) < max_items:
            params = {
                "q": query,
                "fields": fields,
                "pageSize": min(100, max_items - len(all_items)),
            }
            if page_token:
                params["pageToken"] = page_token

            resp = requests.get(
                f"{DRIVE_API_BASE}/files",
                headers=headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            files = data.get("files", [])
            all_items.extend(files)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    print(f"[drive] {len(all_items)}개 미디어 항목 조회됨 ({date_from} ~ {date_to})")
    return all_items


def drive_files_to_media(drive_files):
    """Drive API 응답을 media_files 형식으로 변환 (다운로드 없이 메타데이터만).

    Drive의 imageMediaMetadata에서 GPS/날짜를 직접 추출하여 EXIF 파싱 불필요.
    """
    media_files = []
    for item in drive_files:
        mime = item.get("mimeType", "")
        file_type = "video" if "video" in mime else "image"
        meta = item.get("imageMediaMetadata", {})
        location = meta.get("location", {})

        lat = location.get("latitude")
        lon = location.get("longitude")
        creation_time = item.get("createdTime", item.get("modifiedTime", ""))

        media_files.append({
            "drive_id": item["id"],
            "filename": item.get("name", "photo.jpg"),
            "path": None,  # 아직 다운로드 안 됨
            "type": file_type,
            "modified_time": creation_time,
            "datetime": creation_time,
            "lat": lat,
            "lon": lon,
            "location_name": "",
            "thumbnailLink": item.get("thumbnailLink", ""),
            "size": int(item.get("size", 0)),
        })
    return media_files


def download_drive_files(access_token, media_files, download_dir, max_workers=8):
    """media_files의 drive_id로 실제 파일을 병렬 다운로드.

    Args:
        media_files: drive_files_to_media() 결과 (drive_id 필드 필요)
        max_workers: 동시 다운로드 스레드 수

    Returns:
        다운로드된 파일 수
    """
    os.makedirs(download_dir, exist_ok=True)
    headers = {"Authorization": f"Bearer {access_token}"}

    def _download_one(idx, item):
        drive_id = item.get("drive_id")
        if not drive_id:
            return False
        filename = item["filename"]
        file_path = os.path.join(download_dir, filename)

        # 중복 파일명 처리
        if os.path.exists(file_path):
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{idx}{ext}"
            file_path = os.path.join(download_dir, filename)

        try:
            dl_url = f"{DRIVE_API_BASE}/files/{drive_id}?alt=media"
            resp = requests.get(dl_url, headers=headers, timeout=120, stream=True)
            resp.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in resp.iter_content(32768):
                    f.write(chunk)

            item["path"] = file_path
            item["filename"] = filename
            return True
        except Exception as e:
            print(f"[drive] 다운로드 실패: {item.get('filename', '?')} - {e}")
            return False

    success = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_download_one, i, item): i
            for i, item in enumerate(media_files)
        }
        for future in as_completed(futures):
            if future.result():
                success += 1
                if success % 20 == 0:
                    print(f"[drive] {success}/{len(media_files)} 다운로드 완료")

    print(f"[drive] 총 {success}/{len(media_files)} 다운로드 완료")
    return success
