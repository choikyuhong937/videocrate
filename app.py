#!/usr/bin/env python3
"""VideoCrate Web - 여행 영상 자동 생성 웹 앱."""

import os
import uuid
import json
import shutil
import threading
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_file, url_for

import config
from fetcher import scan_local_folder
from metadata import enrich_media_with_metadata, group_by_location
from selector import select_best_photos
from subtitles import generate_subtitles, write_srt
from video import generate_video

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max upload

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 작업 상태 저장 (메모리)
jobs = {}


def run_pipeline(job_id: str, folder_path: str, options: dict):
    """백그라운드에서 영상 생성 파이프라인을 실행."""
    job = jobs[job_id]

    try:
        # 1단계: 미디어 스캔
        job["step"] = 1
        job["message"] = "미디어 파일을 스캔하고 있습니다..."
        media_files = scan_local_folder(folder_path)
        if not media_files:
            job["status"] = "error"
            job["message"] = "미디어 파일을 찾을 수 없습니다."
            return
        job["total_files"] = len(media_files)

        # 2단계: 메타데이터 파싱
        job["step"] = 2
        job["message"] = "사진 정보를 분석하고 장소별로 분류하고 있습니다..."
        media_files = enrich_media_with_metadata(media_files)
        location_groups = group_by_location(media_files)
        job["total_groups"] = len(location_groups)
        job["groups"] = [
            {"name": g["location_name"], "count": len(g["files"]), "date_range": g.get("date_range", "")}
            for g in location_groups
        ]

        # 3단계: AI 선별
        job["step"] = 3
        job["message"] = "AI가 베스트 사진을 고르고 있습니다..."
        max_per_group = options.get("max_per_group", 5)
        max_photos = options.get("max_photos", 30)
        api_key = options.get("api_key")
        selected = select_best_photos(location_groups, max_per_group=max_per_group, max_total=max_photos, api_key=api_key)
        if not selected:
            job["status"] = "error"
            job["message"] = "선별된 사진이 없습니다."
            return
        job["selected_count"] = len(selected)

        # 4단계: 자막 생성
        job["step"] = 4
        job["message"] = "AI가 감성 자막을 만들고 있습니다..."
        duration = options.get("duration", config.DEFAULT_PHOTO_DURATION)
        lang = options.get("lang", config.DEFAULT_LANG)
        subtitles = generate_subtitles(selected, location_groups, photo_duration=duration, lang=lang, api_key=api_key)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        srt_path = os.path.join(OUTPUT_DIR, f"subtitles_{job_id}.srt")
        write_srt(subtitles, srt_path)
        job["srt_path"] = srt_path

        # 5단계: 영상 생성
        job["step"] = 5
        job["message"] = "영상을 렌더링하고 있습니다... (시간이 좀 걸립니다)"
        output_path = os.path.join(OUTPUT_DIR, f"travel_video_{job_id}.mp4")
        generate_video(
            selected,
            srt_path=srt_path,
            output_path=output_path,
            photo_duration=duration,
        )

        job["status"] = "done"
        job["step"] = 6
        job["message"] = "영상 생성이 완료되었습니다!"
        job["output_path"] = output_path
        job["video_filename"] = f"travel_video_{job_id}.mp4"

    except Exception as e:
        job["status"] = "error"
        job["message"] = f"오류가 발생했습니다: {str(e)}"

    finally:
        # 업로드된 파일 정리
        if os.path.exists(folder_path) and folder_path.startswith(UPLOAD_DIR):
            shutil.rmtree(folder_path, ignore_errors=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    """사진 업로드 및 영상 생성 시작."""
    files = request.files.getlist("photos")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "사진을 업로드해주세요."}), 400

    # 옵션 파싱
    options = {
        "max_photos": int(request.form.get("max_photos", 30)),
        "max_per_group": int(request.form.get("max_per_group", 5)),
        "duration": int(request.form.get("duration", 4)),
        "lang": request.form.get("lang", "ko"),
        "api_key": request.form.get("api_key", "").strip() or None,
    }

    # 파일 저장
    job_id = str(uuid.uuid4())[:8]
    upload_folder = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(upload_folder, exist_ok=True)

    saved_count = 0
    for f in files:
        if f.filename:
            safe_name = f.filename.replace("/", "_").replace("\\", "_")
            f.save(os.path.join(upload_folder, safe_name))
            saved_count += 1

    if saved_count == 0:
        return jsonify({"error": "유효한 파일이 없습니다."}), 400

    # 작업 초기화
    jobs[job_id] = {
        "status": "processing",
        "step": 0,
        "message": "업로드 완료, 처리를 시작합니다...",
        "total_files": 0,
        "total_groups": 0,
        "selected_count": 0,
        "groups": [],
        "uploaded_count": saved_count,
    }

    # 백그라운드 스레드로 파이프라인 실행
    thread = threading.Thread(target=run_pipeline, args=(job_id, upload_folder, options))
    thread.daemon = True
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def status(job_id):
    """작업 진행 상태 조회."""
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

    return jsonify({"error": "잘못된 파일 타입입니다."}), 400


@app.route("/video/<job_id>")
def serve_video(job_id):
    """영상 스트리밍 (비디오 플레이어용)."""
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "영상이 준비되지 않았습니다."}), 404
    return send_file(job["output_path"], mimetype="video/mp4")


if __name__ == "__main__":
    if not config.GEMINI_API_KEY:
        print("[!] GEMINI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    print("VideoCrate Web - http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
