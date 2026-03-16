"""Google OAuth 2.0 + Photos Picker API 연동 모듈.

흐름: OAuth 로그인 → Picker로 사진 선택 → 다운로드 → AI 분류
(Photos Library API 2025-03-31 폐지 → Picker API가 유일한 접근 방법)
"""

import os
import requests
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
PICKER_API_BASE = "https://photospicker.googleapis.com/v1"

SCOPES = [
    "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
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


# ─── Photos Picker API ───

def create_picker_session(access_token):
    """Picker 세션 생성 → pickerUri 반환."""
    resp = requests.post(
        f"{PICKER_API_BASE}/sessions",
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json"},
        json={},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def poll_picker_session(access_token, session_id):
    """Picker 세션 폴링 (사용자 선택 완료 확인)."""
    resp = requests.get(
        f"{PICKER_API_BASE}/sessions/{session_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def list_picker_media_items(access_token, session_id):
    """선택된 미디어 아이템 목록 조회."""
    all_items = []
    page_token = None

    while True:
        url = f"{PICKER_API_BASE}/mediaItems"
        params = {"sessionId": session_id, "pageSize": 100}
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("mediaItems", [])
        all_items.extend(items)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    print(f"[picker] {len(all_items)}개 미디어 아이템 조회됨")
    return all_items


def delete_picker_session(access_token, session_id):
    """Picker 세션 삭제."""
    try:
        requests.delete(
            f"{PICKER_API_BASE}/sessions/{session_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except Exception:
        pass


def picker_items_to_media(picker_items):
    """Picker API 응답을 media_files 형식으로 변환."""
    media_files = []
    for item in picker_items:
        media_type = item.get("type", "PHOTO")
        file_type = "video" if media_type == "VIDEO" else "image"

        # Picker API PickedMediaItem 구조
        media_file = item.get("mediaFile", {})
        creation_time = item.get("createTime", "")
        mime = media_file.get("mimeType", "image/jpeg")
        original_filename = media_file.get("filename", "")

        # 파일명: 원본 파일명 우선, 없으면 ID 기반
        if original_filename:
            filename = original_filename
        else:
            filename = item.get("id", "photo") + (".mp4" if file_type == "video" else ".jpg")

        media_files.append({
            "picker_id": item.get("id", ""),
            "filename": filename,
            "path": None,
            "type": file_type,
            "modified_time": creation_time,
            "datetime": creation_time,
            "lat": None,
            "lon": None,
            "location_name": "",
            "baseUrl": media_file.get("baseUrl", ""),
            "mimeType": mime,
        })
    return media_files


def download_picker_photos(media_files, download_dir, access_token=None, max_workers=8):
    """Picker에서 선택된 사진을 baseUrl로 병렬 다운로드.

    Returns:
        다운로드된 파일 수
    """
    os.makedirs(download_dir, exist_ok=True)

    def _download_one(idx, item):
        base_url = item.get("baseUrl")
        if not base_url:
            print(f"[picker] baseUrl 없음: {item.get('filename', '?')}")
            return False

        filename = item["filename"]
        file_path = os.path.join(download_dir, filename)

        if os.path.exists(file_path):
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{idx}{ext}"
            file_path = os.path.join(download_dir, filename)

        try:
            if item["type"] == "video":
                dl_url = f"{base_url}=dv"
            else:
                dl_url = f"{base_url}=d"

            headers = {}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"

            resp = requests.get(dl_url, headers=headers, timeout=120, stream=True)
            resp.raise_for_status()

            with open(file_path, "wb") as f:
                for chunk in resp.iter_content(32768):
                    f.write(chunk)

            item["path"] = file_path
            item["filename"] = filename
            return True
        except Exception as e:
            print(f"[picker] 다운로드 실패: {item.get('filename', '?')} - {e}")
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
                    print(f"[picker] {success}/{len(media_files)} 다운로드 완료")

    print(f"[picker] 총 {success}/{len(media_files)} 다운로드 완료")
    return success
