"""Google OAuth 2.0 + Photos Library API 연동 모듈.

흐름: OAuth 로그인 → Photos Library API로 날짜 기반 사진 조회 → 다운로드
"""

import os
import requests
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
PHOTOS_API_BASE = "https://photoslibrary.googleapis.com/v1"

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.readonly",
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


# ─── Photos Library API: 날짜 기반 사진 조회 ───

def list_photos_by_date(access_token, date_from, date_to, max_items=500):
    """Google Photos Library API로 날짜 범위의 사진/영상을 조회.

    Args:
        date_from: "YYYY-MM-DD"
        date_to: "YYYY-MM-DD"

    Returns:
        Photos API mediaItems 리스트
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # 날짜 파싱
    from_parts = date_from.split("-")
    to_parts = date_to.split("-")

    body = {
        "pageSize": min(100, max_items),
        "filters": {
            "dateFilter": {
                "ranges": [{
                    "startDate": {
                        "year": int(from_parts[0]),
                        "month": int(from_parts[1]),
                        "day": int(from_parts[2]),
                    },
                    "endDate": {
                        "year": int(to_parts[0]),
                        "month": int(to_parts[1]),
                        "day": int(to_parts[2]),
                    },
                }]
            }
        },
    }

    all_items = []
    page_token = None

    while len(all_items) < max_items:
        if page_token:
            body["pageToken"] = page_token

        resp = requests.post(
            f"{PHOTOS_API_BASE}/mediaItems:search",
            headers=headers,
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("mediaItems", [])
        all_items.extend(items)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    print(f"[photos] {len(all_items)}개 미디어 항목 조회됨 ({date_from} ~ {date_to})")
    return all_items


def photos_to_media(photo_items):
    """Photos Library API 응답을 media_files 형식으로 변환."""
    media_files = []
    for item in photo_items:
        meta = item.get("mediaMetadata", {})
        creation_time = meta.get("creationTime", "")
        mime = item.get("mimeType", "")
        file_type = "video" if "video" in mime else "image"

        # Photos API에서 GPS는 제공하지 않음 (EXIF 다운로드 후 추출 필요)
        media_files.append({
            "photo_id": item["id"],
            "filename": item.get("filename", "photo.jpg"),
            "path": None,
            "type": file_type,
            "modified_time": creation_time,
            "datetime": creation_time,
            "lat": None,
            "lon": None,
            "location_name": "",
            "baseUrl": item.get("baseUrl", ""),
            "width": int(meta.get("width", 0)),
            "height": int(meta.get("height", 0)),
        })
    return media_files


def download_photos(media_files, download_dir, max_workers=8):
    """Photos Library API의 baseUrl로 실제 파일을 병렬 다운로드.

    Returns:
        다운로드된 파일 수
    """
    os.makedirs(download_dir, exist_ok=True)

    def _download_one(idx, item):
        base_url = item.get("baseUrl")
        if not base_url:
            return False

        filename = item["filename"]
        file_path = os.path.join(download_dir, filename)

        if os.path.exists(file_path):
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{idx}{ext}"
            file_path = os.path.join(download_dir, filename)

        try:
            # baseUrl + =d 로 원본 다운로드, =w{max}-h{max} 로 리사이즈
            if item["type"] == "video":
                dl_url = f"{base_url}=dv"
            else:
                dl_url = f"{base_url}=d"

            resp = requests.get(dl_url, timeout=120, stream=True)
            resp.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in resp.iter_content(32768):
                    f.write(chunk)

            item["path"] = file_path
            item["filename"] = filename
            return True
        except Exception as e:
            print(f"[photos] 다운로드 실패: {item.get('filename', '?')} - {e}")
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
                    print(f"[photos] {success}/{len(media_files)} 다운로드 완료")

    print(f"[photos] 총 {success}/{len(media_files)} 다운로드 완료")
    return success
