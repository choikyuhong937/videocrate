#!/usr/bin/env python3
"""VideoCrate Web - 여행 영상 자동 생성 웹 앱.

흐름: 사진 업로드 → 여행 자동 분류 → 여행 선택 → 영상 생성
"""

import os
import uuid
import json
import shutil
import threading
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_file

import config
from fetcher import scan_local_folder
from metadata import enrich_media_with_metadata, group_by_location
from selector import select_best_photos
from subtitles import generate_subtitles, write_srt
from video import generate_video

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 세션/작업 상태 (메모리)
sessions = {}  # upload_id → {folder, media_files, location_groups}
jobs = {}      # job_id → {status, step, message, ...}


# ─── Phase 1: 업로드 & 여행 분류 ───

def analyze_uploads(upload_id: str, folder_path: str):
    """업로드된 사진을 스캔하고 여행별로 자동 분류."""
    session = sessions[upload_id]
    try:
        session["status"] = "scanning"
        session["message"] = "미디어 파일을 스캔하고 있습니다..."
        media_files = scan_local_folder(folder_path)
        if not media_files:
            session["status"] = "error"
            session["message"] = "미디어 파일을 찾을 수 없습니다."
            return

        session["status"] = "analyzing"
        session["message"] = "GPS/날짜 정보를 분석하고 여행을 분류하고 있습니다..."
        media_files = enrich_media_with_metadata(media_files)
        location_groups = group_by_location(media_files)

        # 여행 카드 데이터 구성
        trips = []
        for i, group in enumerate(location_groups):
            image_files = [f for f in group["files"] if f["type"] == "image"]
            video_files = [f for f in group["files"] if f["type"] == "video"]

            # 대표 이미지 (첫 번째 이미지의 파일명)
            thumbnail = image_files[0]["filename"] if image_files else None

            trips.append({
                "id": i,
                "location": group["location_name"],
                "date_range": group.get("date_range", ""),
                "photo_count": len(image_files),
                "video_count": len(video_files),
                "total_count": len(group["files"]),
                "thumbnail": thumbnail,
            })

        session["status"] = "ready"
        session["message"] = "여행 분류 완료!"
        session["media_files"] = media_files
        session["location_groups"] = location_groups
        session["trips"] = trips

    except Exception as e:
        session["status"] = "error"
        session["message"] = f"분석 중 오류: {str(e)}"


@app.route("/")
def root():
    return render_template("index.html")


@app.route("/tripvideo")
def tripvideo():
    return render_template("index.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    """사진 업로드 & 여행 자동 분류 시작."""
    files = request.files.getlist("photos")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "사진을 업로드해주세요."}), 400

    upload_id = str(uuid.uuid4())[:8]
    upload_folder = os.path.join(UPLOAD_DIR, upload_id)
    os.makedirs(upload_folder, exist_ok=True)

    saved_count = 0
    for f in files:
        if f.filename:
            safe_name = f.filename.replace("/", "_").replace("\\", "_")
            f.save(os.path.join(upload_folder, safe_name))
            saved_count += 1

    if saved_count == 0:
        return jsonify({"error": "유효한 파일이 없습니다."}), 400

    sessions[upload_id] = {
        "status": "uploading",
        "message": "업로드 완료, 분석을 시작합니다...",
        "folder": upload_folder,
        "uploaded_count": saved_count,
        "trips": [],
    }

    thread = threading.Thread(target=analyze_uploads, args=(upload_id, upload_folder))
    thread.daemon = True
    thread.start()

    return jsonify({"upload_id": upload_id})


@app.route("/api/analyze/<upload_id>")
def analyze_status(upload_id):
    """업로드 분석 상태 조회."""
    session = sessions.get(upload_id)
    if not session:
        return jsonify({"error": "세션을 찾을 수 없습니다."}), 404
    return jsonify({
        "status": session["status"],
        "message": session["message"],
        "trips": session.get("trips", []),
        "uploaded_count": session.get("uploaded_count", 0),
    })


@app.route("/api/thumbnail/<upload_id>/<filename>")
def thumbnail(upload_id, filename):
    """업로드된 이미지 썸네일 제공."""
    session = sessions.get(upload_id)
    if not session:
        return "", 404
    file_path = os.path.join(session["folder"], filename)
    if not os.path.isfile(file_path):
        return "", 404
    return send_file(file_path, mimetype="image/jpeg")


# ─── Phase 2: 여행 선택 → 영상 생성 ───

def run_pipeline(job_id: str, upload_id: str, selected_trip_ids: list, options: dict):
    """선택된 여행으로 영상 생성 파이프라인 실행."""
    job = jobs[job_id]
    session = sessions.get(upload_id)

    if not session or session["status"] != "ready":
        job["status"] = "error"
        job["message"] = "세션이 만료되었습니다. 다시 업로드해주세요."
        return

    try:
        all_groups = session["location_groups"]
        # 선택된 여행 그룹만 필터
        selected_groups = [all_groups[i] for i in selected_trip_ids if i < len(all_groups)]
        if not selected_groups:
            job["status"] = "error"
            job["message"] = "선택된 여행이 없습니다."
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
    """선택된 여행으로 영상 생성 시작."""
    data = request.get_json()
    upload_id = data.get("upload_id")
    selected_trips = data.get("selected_trips", [])

    if not upload_id or upload_id not in sessions:
        return jsonify({"error": "세션이 만료되었습니다."}), 400
    if not selected_trips:
        return jsonify({"error": "여행을 선택해주세요."}), 400

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
    print("TripVideo - http://localhost:5000/tripvideo")
    app.run(host="0.0.0.0", port=5000, debug=True)
