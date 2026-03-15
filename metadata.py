"""EXIF 메타데이터 파싱 및 장소별 그룹핑 모듈."""

import exifread
import requests
from datetime import datetime
from collections import defaultdict


def _convert_gps_to_decimal(gps_coords, gps_ref) -> float:
    """EXIF GPS 좌표를 10진수로 변환."""
    degrees = float(gps_coords.values[0].num) / float(gps_coords.values[0].den)
    minutes = float(gps_coords.values[1].num) / float(gps_coords.values[1].den)
    seconds = float(gps_coords.values[2].num) / float(gps_coords.values[2].den)

    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
    if gps_ref in ("S", "W"):
        decimal = -decimal
    return round(decimal, 6)


def extract_exif(file_path: str) -> dict:
    """파일에서 EXIF 메타데이터(GPS, 촬영일시)를 추출."""
    result = {"lat": None, "lon": None, "datetime": None}

    try:
        with open(file_path, "rb") as f:
            tags = exifread.process_file(f, details=False)
    except Exception:
        return result

    # 촬영 일시
    for dt_tag in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
        if dt_tag in tags:
            try:
                result["datetime"] = datetime.strptime(
                    str(tags[dt_tag]), "%Y:%m:%d %H:%M:%S"
                ).isoformat()
            except ValueError:
                pass
            break

    # GPS 좌표
    lat_tag = tags.get("GPS GPSLatitude")
    lat_ref = tags.get("GPS GPSLatitudeRef")
    lon_tag = tags.get("GPS GPSLongitude")
    lon_ref = tags.get("GPS GPSLongitudeRef")

    if lat_tag and lat_ref and lon_tag and lon_ref:
        try:
            result["lat"] = _convert_gps_to_decimal(lat_tag, str(lat_ref))
            result["lon"] = _convert_gps_to_decimal(lon_tag, str(lon_ref))
        except (ZeroDivisionError, IndexError, AttributeError):
            pass

    return result


def reverse_geocode(lat: float, lon: float) -> str:
    """GPS 좌표를 장소명으로 변환 (Nominatim 무료 API)."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 14, "accept-language": "ko"},
            headers={"User-Agent": "VideoCrate/1.0"},
            timeout=5,
        )
        data = resp.json()
        address = data.get("address", {})

        # 도시/구/동 수준의 장소명 생성
        parts = []
        for key in ("city", "town", "village", "suburb", "neighbourhood"):
            if key in address:
                parts.append(address[key])
                break
        for key in ("quarter", "neighbourhood", "road"):
            if key in address and address[key] not in parts:
                parts.append(address[key])
                break

        if parts:
            country = address.get("country", "")
            return f"{country} {' '.join(parts)}".strip()

        return data.get("display_name", "알 수 없는 장소").split(",")[0]
    except Exception:
        return f"{lat:.4f}, {lon:.4f}"


def enrich_media_with_metadata(media_files: list[dict]) -> list[dict]:
    """미디어 파일 리스트에 EXIF 메타데이터를 추가."""
    for media in media_files:
        if media["type"] == "image":
            exif = extract_exif(media["path"])
            media["lat"] = exif["lat"]
            media["lon"] = exif["lon"]
            media["datetime"] = exif["datetime"] or media["modified_time"]
        else:
            media["lat"] = None
            media["lon"] = None
            media["datetime"] = media["modified_time"]
    return media_files


def group_by_location(media_files: list[dict], distance_threshold_km: float = 2.0) -> list[dict]:
    """미디어를 장소별로 그룹핑한다.

    GPS가 없는 파일은 시간 기반으로 인접 그룹에 병합.
    """
    import math

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return R * 2 * math.asin(math.sqrt(a))

    # 시간순 정렬
    media_files.sort(key=lambda m: m.get("datetime") or "")

    groups = []
    current_group = None

    for media in media_files:
        lat, lon = media.get("lat"), media.get("lon")

        if current_group is None:
            current_group = {
                "location_name": None,
                "lat": lat,
                "lon": lon,
                "files": [media],
            }
            continue

        # GPS가 있으면 거리로 비교
        if lat and lon and current_group["lat"] and current_group["lon"]:
            dist = haversine(current_group["lat"], current_group["lon"], lat, lon)
            if dist > distance_threshold_km:
                groups.append(current_group)
                current_group = {"location_name": None, "lat": lat, "lon": lon, "files": [media]}
                continue

        # GPS가 없으면 현재 그룹에 추가
        current_group["files"].append(media)
        if lat and lon and current_group["lat"] is None:
            current_group["lat"] = lat
            current_group["lon"] = lon

    if current_group and current_group["files"]:
        groups.append(current_group)

    # 각 그룹에 장소명 추가
    for group in groups:
        if group["lat"] and group["lon"]:
            group["location_name"] = reverse_geocode(group["lat"], group["lon"])
        else:
            group["location_name"] = "알 수 없는 장소"

        dates = [f.get("datetime", "") for f in group["files"] if f.get("datetime")]
        group["date_range"] = f"{min(dates)[:10]} ~ {max(dates)[:10]}" if dates else ""

    print(f"[metadata] {len(groups)}개 장소 그룹으로 분류 완료")
    for g in groups:
        print(f"  - {g['location_name']} ({len(g['files'])}개 파일, {g['date_range']})")

    return groups
