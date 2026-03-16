"""FFmpeg를 사용하여 이미지/영상에서 최종 여행 영상을 생성하는 모듈."""

import subprocess
import os
import json
import tempfile
from pathlib import Path
from PIL import Image

import config


def _prepare_image(file_path: str, output_path: str, resolution: tuple = None):
    """이미지를 16:9로 리사이징/크롭하여 저장."""
    res = resolution or config.DEFAULT_RESOLUTION
    w, h = res

    img = Image.open(file_path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # 16:9 비율로 크롭
    target_ratio = w / h
    img_ratio = img.width / img.height

    if img_ratio > target_ratio:
        new_w = int(img.height * target_ratio)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    else:
        new_h = int(img.width / target_ratio)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))

    img = img.resize((w, h), Image.LANCZOS)
    img.save(output_path, format="JPEG", quality=95)


def generate_video(
    selected_media: list[dict],
    srt_path: str,
    output_path: str,
    photo_duration: int = None,
    music_path: str = None,
    resolution: tuple = None,
):
    """선별된 미디어와 자막으로 최종 영상을 생성한다.

    Ken Burns 효과 + 크로스페이드 트랜지션 + 자막 burn-in.
    """
    duration = photo_duration or config.DEFAULT_PHOTO_DURATION
    res = resolution or config.DEFAULT_RESOLUTION
    w, h = res

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1단계: 각 이미지를 개별 영상 클립으로 변환
        clip_paths = []
        for i, media in enumerate(selected_media):
            clip_path = os.path.join(tmpdir, f"clip_{i:04d}.mp4")

            if media["type"] == "image":
                # 이미지 준비
                prepared = os.path.join(tmpdir, f"img_{i:04d}.jpg")
                _prepare_image(media["path"], prepared, resolution=res)

                # Ken Burns 효과 (줌인)
                # zoompan: 느리게 줌인하면서 약간 패닝
                cmd = [
                    "ffmpeg", "-y",
                    "-threads", "2",
                    "-loop", "1",
                    "-i", prepared,
                    "-vf", (
                        f"zoompan=z='min(zoom+0.0015,1.2)':"
                        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                        f"d={duration * 25}:s={w}x{h}:fps=25,"
                        f"format=yuv420p"
                    ),
                    "-t", str(duration),
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p",
                    clip_path,
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                clip_paths.append(clip_path)

            elif media["type"] == "video":
                # 영상 클립: 리사이징 + 트리밍
                cmd = [
                    "ffmpeg", "-y",
                    "-threads", "2",
                    "-i", media["path"],
                    "-t", str(duration),
                    "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-an",
                    "-pix_fmt", "yuv420p",
                    clip_path,
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                clip_paths.append(clip_path)

        if not clip_paths:
            print("[video] 처리할 클립이 없습니다.")
            return

        print(f"[video] {len(clip_paths)}개 클립 생성 완료, 합치는 중...")

        # 2단계: 클립들을 크로스페이드로 이어 붙이기
        concat_list = os.path.join(tmpdir, "concat.txt")
        with open(concat_list, "w") as f:
            for clip in clip_paths:
                f.write(f"file '{clip}'\n")

        merged_path = os.path.join(tmpdir, "merged.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-threads", "2",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            merged_path,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # 3단계: 자막 burn-in + 배경음악
        print("[video] 자막 합성 중...")
        final_cmd = [
            "ffmpeg", "-y",
            "-threads", "2",
            "-i", merged_path,
        ]

        if music_path and os.path.isfile(music_path):
            final_cmd.extend(["-i", music_path])

        # 자막 필터 - ASS 스타일로 burn-in
        subtitle_filter = (
            f"subtitles={srt_path}:force_style='"
            f"FontSize={config.DEFAULT_FONT_SIZE},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"Outline=2,"
            f"Shadow=1,"
            f"MarginV=30"
            f"'"
        )
        final_cmd.extend(["-vf", subtitle_filter])

        final_cmd.extend([
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
        ])

        if music_path and os.path.isfile(music_path):
            final_cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ])
        else:
            final_cmd.extend(["-an"])

        final_cmd.append(output_path)
        subprocess.run(final_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)

    print(f"[video] 영상 생성 완료: {output_path}")
