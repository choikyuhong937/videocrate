#!/usr/bin/env python3
"""VideoCrate Web - 여행 영상 자동 생성 웹 앱.

흐름: Google 로그인 → Picker로 사진 선택 → AI 테마 자동 분류 → 테마 선택 → 영상 생성
"""

import os
import uuid
import json
import shutil
import threading
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, send_file, redirect, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from metadata import enrich_media_with_metadata, group_by_location
from selector import select_best_photos
from subtitles import generate_subtitles, write_srt
from video import generate_video
from categorizer import categorize_photos
from google_photos import (
    get_auth_url, exchange_code, get_user_info, refresh_access_token,
    create_picker_session, poll_picker_session,
    list_picker_media_items, delete_picker_session,
    picker_items_to_media, download_picker_photos,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB
app.secret_key = config.FLASK_SECRET_KEY
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

sessions_store = {}  # upload_id → {media_files, theme_cards, ...}
jobs = {}            # job_id → {status, step, message, ...}


def _get_redirect_uri():
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host", request.host)
    return f"{scheme}://{host}/auth/callback"


# ─── OAuth Routes ───

@app.route("/auth/google")
def auth_google():
    client_id = config.GOOGLE_CLIENT_ID
    if not client_id:
        return redirect("/tripvideo?error=google_not_configured")

    api_key = request.args.get("api_key", "")
    if api_key:
        session["pending_api_key"] = api_key

    state = str(uuid.uuid4())[:8]
    session["oauth_state"] = state

    redirect_uri = _get_redirect_uri()
    auth_url = get_auth_url(client_id, redirect_uri, state=state)
    return redirect(auth_url)


@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    error = request.args.get("error")
    state = request.args.get("state", "")

    if error:
        return redirect(f"/tripvideo?error={error}")
    if not code:
        return redirect("/tripvideo?error=no_code")

    expected_state = session.pop("oauth_state", "")
    if state != expected_state:
        print(f"[auth] state 불일치: expected={expected_state!r}, got={state!r}")

    try:
        redirect_uri = _get_redirect_uri()
        tokens = exchange_code(
            code, config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET, redirect_uri
        )

        access_token = tokens["access_token"]
        refresh_token = tokens.get("refresh_token", "")
        user_info = get_user_info(access_token)

        session["google_access_token"] = access_token
        session["google_refresh_token"] = refresh_token
        session["google_user"] = {
            "email": user_info.get("email", ""),
            "name": user_info.get("name", ""),
            "picture": user_info.get("picture", ""),
        }
        session.modified = True
        print(f"[auth] 로그인 성공: {user_info.get('email')}")

        return redirect("/tripvideo?logged_in=1")

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"""<html><body style="background:#111;color:#eee;font-family:monospace;padding:20px">
        <h2 style="color:#f87171">OAuth 에러</h2>
        <p>{str(e)}</p>
        <p><a href="/tripvideo" style="color:#a594ff">← 돌아가기</a></p>
        </body></html>""", 500


@app.route("/auth/logout")
def auth_logout():
    session.clear()
    return redirect("/tripvideo")


@app.route("/api/user")
def api_user():
    google_user = session.get("google_user")
    if google_user:
        return jsonify({
            "logged_in": True,
            "email": google_user["email"],
            "name": google_user["name"],
            "picture": google_user["picture"],
        })
    return jsonify({"logged_in": False})


@app.route("/auth/debug")
def auth_debug():
    has_token = bool(session.get("google_access_token"))
    has_user = bool(session.get("google_user"))
    return jsonify({
        "has_token": has_token,
        "has_user": has_user,
        "user_email": session.get("google_user", {}).get("email", "없음"),
    })


# ─── Picker API ───

@app.route("/api/picker/create-session", methods=["POST"])
def picker_create():
    access_token = session.get("google_access_token")
    if not access_token:
        return jsonify({"error": "Google 로그인이 필요합니다."}), 401
    try:
        result = create_picker_session(access_token)
        session["picker_session_id"] = result.get("id", "")
        return jsonify(result)
    except Exception as e:
        print(f"[picker] 세션 생성 에러: {e}")
        return jsonify({"error": f"Picker 세션 생성 실패: {str(e)}"}), 500


@app.route("/api/picker/poll/<session_id>")
def picker_poll(session_id):
    access_token = session.get("google_access_token")
    if not access_token:
        return jsonify({"error": "로그인 필요"}), 401
    try:
        result = poll_picker_session(access_token, session_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def process_picker_photos(upload_id, access_token, picker_session_id, api_key):
    """Picker 선택 사진 → 다운로드 → EXIF → 위치 그룹핑 → AI 분류."""
    sess = sessions_store[upload_id]
    try:
        # 1. 선택된 미디어 목록
        sess["status"] = "fetching"
        sess["message"] = "선택한 사진 정보를 가져오고 있습니다..."
        items = list_picker_media_items(access_token, picker_session_id)

        if not items:
            sess["status"] = "error"
            sess["message"] = "선택된 사진이 없습니다."
            return

        media_files = picker_items_to_media(items)
        sess["uploaded_count"] = len(media_files)
        sess["message"] = f"{len(media_files)}개 사진을 다운로드하고 있습니다..."

        # 2. 다운로드 (병렬)
        download_dir = os.path.join(UPLOAD_DIR, upload_id)
        downloaded = download_picker_photos(media_files, download_dir, access_token=access_token)

        # 다운로드 실패한 파일 제거
        media_files = [f for f in media_files if f.get("path")]
        if not media_files:
            sess["status"] = "error"
            sess["message"] = "사진을 다운로드할 수 없습니다."
            return

        sess["folder"] = download_dir

        # 3. EXIF + 위치 그룹핑
        sess["status"] = "analyzing"
        sess["message"] = "GPS/날짜 정보를 분석하고 있습니다..."
        media_files = enrich_media_with_metadata(media_files)
        location_groups = group_by_location(media_files)

        # 4. AI 테마 분류
        sess["status"] = "categorizing"
        sess["message"] = "AI가 사진을 테마별로 분류하고 있습니다..."
        theme_cards = categorize_photos(media_files, location_groups, api_key=api_key)

        sess["status"] = "ready"
        sess["message"] = "테마 분류 완료!"
        sess["media_files"] = media_files
        sess["location_groups"] = location_groups
        sess["theme_cards"] = theme_cards

        delete_picker_session(access_token, picker_session_id)

    except Exception as e:
        sess["status"] = "error"
        sess["message"] = f"사진 처리 중 오류: {str(e)}"
        print(f"[picker] process error: {e}")


@app.route("/api/picker/fetch", methods=["POST"])
def picker_fetch():
    access_token = session.get("google_access_token")
    if not access_token:
        return jsonify({"error": "Google 로그인이 필요합니다."}), 401

    data = request.get_json() or {}
    picker_session_id = data.get("picker_session_id")
    if not picker_session_id:
        return jsonify({"error": "Picker 세션 ID가 없습니다."}), 400

    upload_id = str(uuid.uuid4())[:8]
    sessions_store[upload_id] = {
        "status": "fetching",
        "message": "사진을 가져오고 있습니다...",
        "folder": "",
        "uploaded_count": 0,
    }

    api_key = session.get("pending_api_key") or config.GEMINI_API_KEY

    thread = threading.Thread(
        target=process_picker_photos,
        args=(upload_id, access_token, picker_session_id, api_key),
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


# ─── Status & Thumbnails ───

@app.route("/api/analyze/<upload_id>")
def analyze_status(upload_id):
    s = sessions_store.get(upload_id)
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
    s = sessions_store.get(upload_id)
    if not s or not s.get("folder"):
        return "", 404
    file_path = os.path.join(s["folder"], filename)
    if not os.path.isfile(file_path):
        return "", 404
    return send_file(file_path, mimetype="image/jpeg")


# ─── 영상 생성 ───

def run_pipeline(job_id, upload_id, selected_trip_ids, options):
    job = jobs[job_id]
    s = sessions_store.get(upload_id)

    if not s or s["status"] != "ready":
        job["status"] = "error"
        job["message"] = "세션이 만료되었습니다."
        return

    try:
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
        selected = select_best_photos(
            selected_groups,
            max_per_group=options.get("max_per_group", 5),
            max_total=options.get("max_photos", 30),
            api_key=api_key,
        )

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
    data = request.get_json()
    upload_id = data.get("upload_id")
    selected_trips = data.get("selected_trips", [])

    if not upload_id or upload_id not in sessions_store:
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
        "status": "processing", "step": 0,
        "message": "영상 생성을 준비하고 있습니다...",
        "total_files": 0, "total_groups": 0, "selected_count": 0,
    }

    thread = threading.Thread(target=run_pipeline, args=(job_id, upload_id, selected_trips, options))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "작업을 찾을 수 없습니다."}), 404
    return jsonify(job)


@app.route("/api/download/<job_id>/<file_type>")
def download(job_id, file_type):
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
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "영상이 준비되지 않았습니다."}), 404
    return send_file(job["output_path"], mimetype="video/mp4")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"TripVideo - http://localhost:{port}/tripvideo")
    app.run(host="0.0.0.0", port=port, debug=True)
