"""Google OAuth 2.0 + Drive API 연동 모듈.

흐름: OAuth 로그인 → Drive API로 날짜 기반 사진 조회 → 다운로드
(Photos Library API는 2025-03-31 폐지 → Drive API로 대체)
"""

import os
import requests
from urllib.parse import urlencode

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
    """Google Drive에서 날짜 범위로 사진/영상을 조회.

    Args:
        access_token: OAuth 액세스 토큰
        date_from: 시작일 (YYYY-MM-DD)
        date_to: 종료일 (YYYY-MM-DD)
        max_items: 최대 조회 수

    Returns:
        Drive 파일 목록 [{id, name, mimeType, createdTime, imageMediaMetadata, ...}]
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    # Drive API 쿼리: 이미지/영상 + 날짜 범위 + 휴지통 제외
    query_parts = [
        "(mimeType contains 'image/' or mimeType contains 'video/')",
        f"createdTime >= '{date_from}T00:00:00'",
        f"createdTime <= '{date_to}T23:59:59'",
        "trashed = false",
    ]
    query = " and ".join(query_parts)

    fields = "nextPageToken,files(id,name,mimeType,createdTime,modifiedTime,imageMediaMetadata,size,thumbnailLink)"

    all_items = []
    page_token = None

    while len(all_items) < max_items:
        params = {
            "q": query,
            "fields": fields,
            "pageSize": min(100, max_items - len(all_items)),
            "orderBy": "createdTime",
            "spaces": "photos",
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


def download_drive_files(access_token, drive_files, download_dir):
    """Drive 파일을 로컬에 다운로드.

    Returns:
        fetcher 호환 형식의 미디어 파일 리스트
    """
    os.makedirs(download_dir, exist_ok=True)
    headers = {"Authorization": f"Bearer {access_token}"}
    downloaded = []

    for idx, item in enumerate(drive_files):
        try:
            file_id = item["id"]
            mime = item.get("mimeType", "")
            filename = item.get("name", f"photo_{idx}.jpg")

            # 중복 파일명 처리
            file_path = os.path.join(download_dir, filename)
            if os.path.exists(file_path):
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{idx}{ext}"
                file_path = os.path.join(download_dir, filename)

            file_type = "video" if "video" in mime else "image"

            # Drive API로 파일 다운로드
            dl_url = f"{DRIVE_API_BASE}/files/{file_id}?alt=media"
            resp = requests.get(dl_url, headers=headers, timeout=120, stream=True)
            resp.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)

            creation_time = item.get("createdTime", item.get("modifiedTime", ""))

            downloaded.append({
                "path": file_path,
                "filename": filename,
                "type": file_type,
                "modified_time": creation_time,
            })

            if (idx + 1) % 20 == 0:
                print(f"[drive] {idx + 1}/{len(drive_files)} 다운로드 완료")

        except Exception as e:
            print(f"[drive] 다운로드 실패: {item.get('name', '?')} - {e}")

    print(f"[drive] 총 {len(downloaded)}/{len(drive_files)} 다운로드 완료")
    return downloaded
