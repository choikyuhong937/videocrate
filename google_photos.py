"""Google Photos OAuth 2.0 + Library API 연동 모듈.

흐름: OAuth 로그인 → 사진 목록 조회 → 다운로드 → 여행 분류
"""

import os
import requests
from urllib.parse import urlencode

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


def list_media_items(access_token, date_from=None, date_to=None, max_items=500):
    """Google Photos에서 미디어 목록 조회.

    Args:
        access_token: OAuth 액세스 토큰
        date_from: 시작일 (YYYY-MM-DD)
        date_to: 종료일 (YYYY-MM-DD)
        max_items: 최대 조회 수
    """
    url = f"{PHOTOS_API_BASE}/mediaItems:search"
    headers = {"Authorization": f"Bearer {access_token}"}

    filters = {}
    if date_from or date_to:
        range_obj = {}
        if date_from:
            parts = date_from.split("-")
            range_obj["startDate"] = {
                "year": int(parts[0]), "month": int(parts[1]), "day": int(parts[2])
            }
        if date_to:
            parts = date_to.split("-")
            range_obj["endDate"] = {
                "year": int(parts[0]), "month": int(parts[1]), "day": int(parts[2])
            }
        filters["dateFilter"] = {"ranges": [range_obj]}

    all_items = []
    page_token = None

    while len(all_items) < max_items:
        body = {"pageSize": min(100, max_items - len(all_items))}
        if filters:
            body["filters"] = filters
        if page_token:
            body["pageToken"] = page_token

        resp = requests.post(url, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("mediaItems", [])
        all_items.extend(items)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    print(f"[google_photos] {len(all_items)}개 미디어 항목 조회됨")
    return all_items


def download_media(media_items, download_dir):
    """미디어 아이템을 로컬에 다운로드.

    Returns:
        fetcher 호환 형식의 미디어 파일 리스트
    """
    os.makedirs(download_dir, exist_ok=True)
    downloaded = []

    for idx, item in enumerate(media_items):
        try:
            base_url = item.get("baseUrl")
            if not base_url:
                continue

            mime = item.get("mimeType", "")
            filename = item.get("filename", f"photo_{idx}.jpg")

            # 중복 파일명 처리
            file_path = os.path.join(download_dir, filename)
            if os.path.exists(file_path):
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{idx}{ext}"
                file_path = os.path.join(download_dir, filename)

            if "video" in mime:
                dl_url = f"{base_url}=dv"
                file_type = "video"
            else:
                dl_url = f"{base_url}=d"
                file_type = "image"

            resp = requests.get(dl_url, timeout=120, stream=True)
            resp.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)

            metadata = item.get("mediaMetadata", {})
            creation_time = metadata.get("creationTime", "")

            downloaded.append({
                "path": file_path,
                "filename": filename,
                "type": file_type,
                "modified_time": creation_time,
            })

            if (idx + 1) % 20 == 0:
                print(f"[google_photos] {idx + 1}/{len(media_items)} 다운로드 완료")

        except Exception as e:
            print(f"[google_photos] 다운로드 실패: {item.get('filename', '?')} - {e}")

    print(f"[google_photos] 총 {len(downloaded)}/{len(media_items)} 다운로드 완료")
    return downloaded
