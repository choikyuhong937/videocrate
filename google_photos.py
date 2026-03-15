"""Google Photos OAuth 2.0 + Picker API 연동 모듈.

흐름: OAuth 로그인 → Picker 세션 생성 → 사용자 사진 선택 → 다운로드
(Photos Library API는 2025-03-31 폐지 → Picker API로 대체)
"""

import os
import requests
from urllib.parse import urlencode

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


# ─── Picker API ───

def create_picker_session(access_token):
    """Picker 세션을 생성하고 pickerUri와 sessionId를 반환."""
    resp = requests.post(
        f"{PICKER_API_BASE}/sessions",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "id": data.get("id", ""),
        "pickerUri": data.get("pickerUri", ""),
        "pollingConfig": data.get("pollingConfig", {}),
        "mediaItemsSet": data.get("mediaItemsSet", False),
    }


def poll_picker_session(access_token, session_id):
    """Picker 세션 상태를 조회 (사용자가 사진 선택을 완료했는지 확인)."""
    resp = requests.get(
        f"{PICKER_API_BASE}/sessions/{session_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "mediaItemsSet": data.get("mediaItemsSet", False),
        "pollingConfig": data.get("pollingConfig", {}),
    }


def list_picker_media_items(access_token, session_id):
    """Picker 세션에서 선택된 미디어 아이템 목록을 조회."""
    all_items = []
    page_token = None

    while True:
        params = {"sessionId": session_id, "pageSize": 100}
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(
            f"{PICKER_API_BASE}/mediaItems",
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

    print(f"[picker] {len(all_items)}개 미디어 항목 선택됨")
    return all_items


def delete_picker_session(access_token, session_id):
    """Picker 세션 삭제 (정리)."""
    try:
        requests.delete(
            f"{PICKER_API_BASE}/sessions/{session_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except Exception as e:
        print(f"[picker] 세션 삭제 실패 (무시): {e}")


def download_media(media_items, download_dir):
    """미디어 아이템을 로컬에 다운로드.

    Picker API의 mediaItems 형식에 맞게 처리.
    Returns:
        fetcher 호환 형식의 미디어 파일 리스트
    """
    os.makedirs(download_dir, exist_ok=True)
    downloaded = []

    for idx, item in enumerate(media_items):
        try:
            # Picker API 응답 형식: mediaFile.baseUrl
            media_file = item.get("mediaFile", {})
            base_url = media_file.get("baseUrl") or item.get("baseUrl")
            if not base_url:
                continue

            mime = media_file.get("mimeType", item.get("mimeType", ""))
            filename = media_file.get("filename", item.get("filename", f"photo_{idx}.jpg"))

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

            # Picker API: createTime은 최상위 또는 mediaFile.mediaMetadata 안에 있음
            creation_time = item.get("createTime", "")
            metadata = media_file.get("mediaMetadata", {})
            if not creation_time:
                creation_time = metadata.get("creationTime", "")

            downloaded.append({
                "path": file_path,
                "filename": filename,
                "type": file_type,
                "modified_time": creation_time,
            })

            if (idx + 1) % 20 == 0:
                print(f"[picker] {idx + 1}/{len(media_items)} 다운로드 완료")

        except Exception as e:
            print(f"[picker] 다운로드 실패: {item.get('filename', '?')} - {e}")

    print(f"[picker] 총 {len(downloaded)}/{len(media_items)} 다운로드 완료")
    return downloaded
