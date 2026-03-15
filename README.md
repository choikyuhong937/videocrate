# VideoCrate

여행 사진/영상을 자동으로 유튜브 스타일 영상으로 만들어주는 CLI 도구.

- EXIF GPS 데이터로 장소별 자동 그룹핑
- Gemini AI로 베스트 사진 자동 선별
- Gemini AI로 감성 자막 + 장소 타이틀 자동 생성
- FFmpeg Ken Burns 효과 + 트랜지션 + 자막 burn-in

## 설치

```bash
pip install -r requirements.txt
# FFmpeg 필요: sudo apt install ffmpeg
```

## 설정

```bash
cp .env.example .env
# .env 파일에 Gemini API 키 입력
```

## 사용법

```bash
# 기본 사용
python main.py --path ~/Photos/tokyo_trip

# 날짜 범위 지정
python main.py --path ~/Photos/trip --from-date 2024-03-10 --to-date 2024-03-20

# 옵션
python main.py --path ~/Photos/trip \
  --max-photos 20 \
  --max-per-group 3 \
  --duration 5 \
  --music ~/Music/bgm.mp3 \
  --lang ko
```

## 출력

- `output/travel_video_YYYYMMDD_HHMMSS.mp4` - 생성된 영상
- `output/subtitles_YYYYMMDD_HHMMSS.srt` - 자막 파일
