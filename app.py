#!/usr/bin/env python3
"""VideoCrate Web - 여행 영상 자동 생성 웹 앱.

흐름: Google 로그인 → 날짜 범위 선택 → Drive API로 사진 자동 조회 → AI 테마 분류 → 영상 생성
"""

import os
import uuid
import json
import shutil
import threading
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, send_file, redirect, session, url_for

import config
from fetcher import scan_local_folder
from metadata import enrich_media_with_metadata, group_by_location
from selector import select_best_photos
from subtitles import generate_subtitles, write_srt
from video import generate_video
from categorizer import categorize_photos
from google_photos import (
    get_auth_url, exchange_code, get_user_info,
    refresh_access_token, list_photos_by_date, download_drive_files,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB
app.secret_key = config.FLASK_SECRET_KEY

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 세션/작업 상태 (메모리)
sessions = {}  # upload_id → {folder, media_files, location_groups}
jobs = {}      # job_id → {status, step, message, ...}


def _get_redirect_uri():
    """OAuth 콜백 URI를 현재 요청 기반으로 생성."""
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    return f"{scheme}://{host}/auth/callback"


# ─── OAuth Routes ───

@app.route("/auth/google")
def auth_google():
    """Google OAuth 시작 - Google 로그인 페이지로 리디렉트."""
    client_id = config.GOOGLE_CLIENT_ID
    if not client_id:
        return redirect("/tripvideo?error=google_not_configured")

    # API key를 세션에 임시 저장 (OAuth 콜백 후 복원용)
    api_key = request.args.get("api_key", "")
    if api_key:
        session["pending_api_key"] = api_key

    # state는 CSRF 방지용 랜덤 토큰
    state = str(uuid.uuid4())[:8]
    session["oauth_state"] = state

    redirect_uri = _get_redirect_uri()
    auth_url = get_auth_url(client_id, redirect_uri, state=state)
    return redirect(auth_url)


@app.route("/auth/callback")
def auth_callback():
    """Google OAuth 콜백 - 토큰 교환 후 메인 페이지로."""
    code = request.args.get("code")
    error = request.args.get("error")
    state = request.args.get("state", "")

    if error:
        return redirect(f"/tripvideo?error={error}")

    if not code:
        return redirect("/tripvideo?error=no_code")

    # CSRF 검증
    expected_state = session.pop("oauth_state", "")
    if state != expected_state:
        return redirect("/tripvideo?error=invalid_state")

    try:
        redirect_uri = _get_redirect_uri()
        tokens = exchange_code(
            code, config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET, redirect_uri
        )

        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")

        # 사용자 정보 조회
        user_info = get_user_info(access_token)

        # 세션에 저장
        session["google_access_token"] = access_token
        session["google_refresh_token"] = refresh_token
        session["google_user"] = {
            "email": user_info.get("email", ""),
            "name": user_info.get("name", ""),
            "picture": user_info.get("picture", ""),
        }

        return redirect("/tripvideo?logged_in=1")

    except Exception as e:
        print(f"[auth] OAuth 에러: {e}")
        return redirect(f"/tripvideo?error=auth_failed")


@app.route("/auth/logout")
def auth_logout():
    """로그아웃."""
    session.clear()
    return redirect("/tripvideo")


@app.route("/api/user")
def api_user():
    """현재 로그인 사용자 정보."""
    google_user = session.get("google_user")
    if google_user:
        return jsonify({
            "logged_in": True,
            "email": google_user["email"],
            "name": google_user["name"],
            "picture": google_user["picture"],
        })
    return jsonify({"logged_in": False})


# ─── Google Drive: 날짜 기반 사진 조회 ───

def fetch_photos_by_date(upload_id, access_token, date_from, date_to, api_key):
    """Drive API로 날짜 범위의 사진을 조회 → 다운로드 → AI 테마 분류."""
    sess = sessions[upload_id]
    try:
        # 1단계: Drive API로 사진 목록 조회
        sess["status"] = "fetching"
        sess["message"] = f"{date_from} ~ {date_to} 사진을 검색하고 있습니다..."

        drive_files = list_photos_by_date(access_token, date_from, date_to)

        if not drive_files:
            sess["status"] = "error"
            sess["message"] = "해당 기간에 사진이 없습니다. 다른 날짜를 선택해주세요."
            return

        sess["message"] = f"{len(drive_files)}개 사진을 다운로드하고 있습니다..."

        # 2단계: 다운로드
        download_dir = os.path.join(UPLOAD_DIR, upload_id)
        media_files = download_drive_files(access_token, drive_files, download_dir)

        if not media_files:
            sess["status"] = "error"
            sess["message"] = "사진을 다운로드할 수 없습니다."
            return

        sess["folder"] = download_dir
        sess["uploaded_count"] = len(media_files)

        # 3단계: EXIF 분석 + 위치 그룹핑
        sess["status"] = "analyzing"
        sess["message"] = "GPS/날짜 정보를 분석하고 있습니다..."

        media_files = enrich_media_with_metadata(media_files)
        location_groups = group_by_location(media_files)

        # 4단계: AI 테마 분류
        sess["status"] = "categorizing"
        sess["message"] = "AI가 사진을 테마별로 분류하고 있습니다..."

        theme_cards = categorize_photos(media_files, location_groups, api_key=api_key)

        sess["status"] = "ready"
        sess["message"] = "테마 분류 완료!"
        sess["media_files"] = media_files
        sess["location_groups"] = location_groups
        sess["theme_cards"] = theme_cards

    except Exception as e:
        sess["status"] = "error"
        sess["message"] = f"사진 조회 중 오류: {str(e)}"
        print(f"[drive] fetch error: {e}")


@app.route("/api/fetch-by-date", methods=["POST"])
def api_fetch_by_date():
    """날짜 범위로 Google Drive에서 사진 조회 & AI 분류 시작."""
    access_token = session.get("google_access_token")
    if not access_token:
        return jsonify({"error": "Google 로그인이 필요합니다."}), 401

    data = request.get_json() or {}
    date_from = data.get("date_from")
    date_to = data.get("date_to")

    if not date_from or not date_to:
        return jsonify({"error": "시작일과 종료일을 선택해주세요."}), 400

    upload_id = str(uuid.uuid4())[:8]
    sessions[upload_id] = {
        "status": "fetching",
        "message": "사진을 검색하고 있습니다...",
        "folder": "",
        "uploaded_count": 0,
    }

    api_key = session.get("pending_api_key") or config.GEMINI_API_KEY

    thread = threading.Thread(
        target=fetch_photos_by_date,
        args=(upload_id, access_token, date_from, date_to, api_key),
    )
    thread.daemon = True
    thread.start()

    return jsonify({"upload_id": upload_id})


# ─── Pages ───

@app.route("/")
def root():
    return render_template("index.html")


@app.route("/tripvideo")
def tripvideo():
    return render_template("index.html")


# ─── Analyze Status ───

@app.route("/api/analyze/<upload_id>")
def analyze_status(upload_id):
    """분석 상태 조회."""
    s = sessions.get(upload_id)
    if not s:
        return jsonify({"error": "세션을 찾을 수 없습니다."}), 404
    return jsonify({
        "status": s["status"],
        "message": s["message"],
        "theme_cards": s.get("theme_cards", []),
        "uploaded_count": s.get("uploaded_count", 0),
    })


@app.route("/api/thumbnail/<upload_id>/<filename>")
def thumbnail(upload_id, filename):
    """업로드된 이미지 썸네일 제공."""
    s = sessions.get(upload_id)
    if not s:
        return "", 404
    file_path = os.path.join(s["folder"], filename)
    if not os.path.isfile(file_path):
        return "", 404
    return send_file(file_path, mimetype="image/jpeg")


# ─── Phase 2: 테마 선택 → 영상 생성 ───

def run_pipeline(job_id: str, upload_id: str, selected_trip_ids: list, options: dict):
    """선택된 테마로 영상 생성 파이프라인 실행."""
    job = jobs[job_id]
    s = sessions.get(upload_id)

    if not s or s["status"] != "ready":
        job["status"] = "error"
        job["message"] = "세션이 만료되었습니다. 다시 시도해주세요."
        return

    try:
        # 테마 카드에서 선택된 그룹 구성 (location_groups 호환 포맷)
        theme_cards = s.get("theme_cards", [])
        selected_groups = []
        for i in selected_trip_ids:
            if i < len(theme_cards):
                t = theme_cards[i]
                selected_groups.append({
                    "location_name": t["name"],
                    "files": t["files"],
                    "date_range": t.get("date_range", ""),
                })
        if not selected_groups:
            job["status"] = "error"
            job["message"] = "선택된 테마가 없습니다."
            return

        total_files = sum(len(g["files"]) for g in selected_groups)
        job["total_files"] = total_files
        job["total_groups"] = len(selected_groups)

        # 1단계: AI 선별
        job["step"] = 1
        job["message"] = "AI가 베스트 사진을 고르고 있습니다..."
        api_key = options.get("api_key")
        max_per_group = options.get("max_per_group", 5)
        max_photos = options.get("max_photos", 30)
        selected = select_best_photos(selected_groups, max_per_group=max_per_group, max_total=max_photos, api_key=api_key)

        if not selected:
            job["status"] = "error"
            job["message"] = "선별된 사진이 없습니다."
            return
        job["selected_count"] = len(selected)

        # 2단계: 자막 생성
        job["step"] = 2
        job["message"] = "AI가 감성 자막을 만들고 있습니다..."
        duration = options.get("duration", config.DEFAULT_PHOTO_DURATION)
        lang = options.get("lang", config.DEFAULT_LANG)
        subs = generate_subtitles(selected, selected_groups, photo_duration=duration, lang=lang, api_key=api_key)

        srt_path = os.path.join(OUTPUT_DIR, f"subtitles_{job_id}.srt")
        write_srt(subs, srt_path)
        job["srt_path"] = srt_path

        # 3단계: 영상 렌더링
        job["step"] = 3
        job["message"] = "영상을 렌더링하고 있습니다..."
        output_path = os.path.join(OUTPUT_DIR, f"travel_video_{job_id}.mp4")
        generate_video(selected, srt_path=srt_path, output_path=output_path, photo_duration=duration)

        job["status"] = "done"
        job["step"] = 4
        job["message"] = "영상 생성 완료!"
        job["output_path"] = output_path
        job["video_filename"] = f"travel_video_{job_id}.mp4"

    except Exception as e:
        job["status"] = "error"
        job["message"] = f"오류: {str(e)}"


@app.route("/api/generate", methods=["POST"])
def generate():
    """선택된 테마로 영상 생성 시작."""
    data = request.get_json()
    upload_id = data.get("upload_id")
    selected_trips = data.get("selected_trips", [])

    if not upload_id or upload_id not in sessions:
        return jsonify({"error": "세션이 만료되었습니다."}), 400
    if not selected_trips:
        return jsonify({"error": "테마를 선택해주세요."}), 400

    options = {
        "max_photos": data.get("max_photos", 30),
        "max_per_group": data.get("max_per_group", 5),
        "duration": data.get("duration", 4),
        "lang": data.get("lang", "ko"),
        "api_key": data.get("api_key", "").strip() or None,
    }

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "processing",
        "step": 0,
        "message": "영상 생성을 준비하고 있습니다...",
        "total_files": 0,
        "total_groups": 0,
        "selected_count": 0,
    }

    thread = threading.Thread(target=run_pipeline, args=(job_id, upload_id, selected_trips, options))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def status(job_id):
    """영상 생성 진행 상태 조회."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "작업을 찾을 수 없습니다."}), 404
    return jsonify(job)


@app.route("/api/download/<job_id>/<file_type>")
def download(job_id, file_type):
    """생성된 파일 다운로드."""
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "파일이 준비되지 않았습니다."}), 404
    if file_type == "video":
        return send_file(job["output_path"], as_attachment=True, download_name="travel_video.mp4")
    elif file_type == "srt":
        return send_file(job["srt_path"], as_attachment=True, download_name="subtitles.srt")
    return jsonify({"error": "잘못된 파일 타입"}), 400


@app.route("/video/<job_id>")
def serve_video(job_id):
    """영상 스트리밍."""
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "영상이 준비되지 않았습니다."}), 404
    return send_file(job["output_path"], mimetype="video/mp4")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"TripVideo - http://localhost:{port}/tripvideo")
    app.run(host="0.0.0.0", port=port, debug=True)
