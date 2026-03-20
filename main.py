#!/usr/bin/env python3
"""VideoCrate - 구글포토 여행 영상 자동 생성기

로컬 사진 폴더에서 장소/시간별로 그룹핑하고,
Gemini AI로 베스트 사진 선별 + 감성 자막을 생성한 뒤,
FFmpeg로 유튜브 스타일 여행 영상을 만듭니다.
"""

import argparse
import os
from datetime import datetime

import config
from fetcher import scan_local_folder
from metadata import enrich_media_with_metadata, group_by_location
from selector import select_best_photos
from subtitles import generate_subtitles, write_srt
from video import generate_video


def main():
    parser = argparse.ArgumentParser(
        description="VideoCrate - 여행 사진/영상으로 유튜브 영상 자동 생성",
    )
    parser.add_argument(
        "--source", choices=["local"], default="local",
        help="미디어 소스 (현재 local만 지원)",
    )
    parser.add_argument(
        "--path", required=True,
        help="사진/영상이 있는 로컬 폴더 경로",
    )
    parser.add_argument("--from-date", dest="from_date", help="시작 날짜 (YYYY-MM-DD)")
    parser.add_argument("--to-date", dest="to_date", help="종료 날짜 (YYYY-MM-DD)")
    parser.add_argument(
        "--max-photos", type=int, default=config.DEFAULT_MAX_PHOTOS,
        help=f"최대 선택 사진 수 (기본: {config.DEFAULT_MAX_PHOTOS})",
    )
    parser.add_argument(
        "--max-per-group", type=int, default=5,
        help="장소별 최대 선택 수 (기본: 5)",
    )
    parser.add_argument(
        "--duration", type=int, default=config.DEFAULT_PHOTO_DURATION,
        help=f"사진당 표시 시간 초 (기본: {config.DEFAULT_PHOTO_DURATION})",
    )
    parser.add_argument("--music", help="배경음악 MP3 파일 경로")
    parser.add_argument(
        "--lang", default=config.DEFAULT_LANG,
        help=f"자막 언어 (기본: {config.DEFAULT_LANG})",
    )
    parser.add_argument(
        "--output", default=None,
        help="출력 파일 경로 (기본: output/travel_video_날짜.mp4)",
    )

    args = parser.parse_args()

    # API 키 확인
    if not config.GEMINI_API_KEY:
        print("[!] GEMINI_API_KEY가 설정되지 않았습니다.")
        print("    .env 파일에 GEMINI_API_KEY=your_key 를 추가하세요.")
        return

    print("=" * 50)
    print("  VideoCrate - 여행 영상 자동 생성기")
    print("=" * 50)

    # 1. 미디어 파일 스캔
    print("\n[1/5] 미디어 파일 스캔 중...")
    media_files = scan_local_folder(args.path, args.from_date, args.to_date)
    if not media_files:
        print("[!] 미디어 파일을 찾을 수 없습니다.")
        return

    # 2. 메타데이터 파싱 & 장소 그룹핑
    print("\n[2/5] 메타데이터 분석 & 장소별 그룹핑 중...")
    media_files = enrich_media_with_metadata(media_files)
    location_groups = group_by_location(media_files)

    # 3. Gemini AI로 베스트 사진 선별
    print("\n[3/5] AI가 베스트 사진을 선별하는 중...")
    selected = select_best_photos(
        location_groups,
        max_per_group=args.max_per_group,
        max_total=args.max_photos,
    )
    if not selected:
        print("[!] 선별된 미디어가 없습니다.")
        return

    # 4. Gemini AI로 자막 생성
    print("\n[4/5] AI가 자막을 생성하는 중...")
    subtitles = generate_subtitles(
        selected, location_groups,
        photo_duration=args.duration,
        lang=args.lang,
    )

    # SRT 파일 저장
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    srt_path = f"output/subtitles_{timestamp}.srt"
    write_srt(subtitles, srt_path)

    # 5. FFmpeg로 영상 생성
    print("\n[5/5] 영상 생성 중... (시간이 좀 걸릴 수 있습니다)")
    output_path = args.output or f"output/travel_video_{timestamp}.mp4"
    generate_video(
        selected,
        srt_path=srt_path,
        output_path=output_path,
        photo_duration=args.duration,
        music_path=args.music,
    )

    print("\n" + "=" * 50)
    print(f"  완료! 영상이 생성되었습니다:")
    print(f"  📹 {output_path}")
    print(f"  📝 {srt_path}")
    print("=" * 50)


if __name__ == "__main__":
    main()
