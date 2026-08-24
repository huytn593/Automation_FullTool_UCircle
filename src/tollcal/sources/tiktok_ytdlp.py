import os
import re
import time
import random
from pathlib import Path
from typing import List, Optional, Dict, Any
import httpx
import yt_dlp

from tollcal.domain.errors import (
    SourceExtractionError,
    SourceNotFoundError,
)
from tollcal.domain.models import SourceVideo
from tollcal.observability.logging import logger
from tollcal.sources.base import SourceAdapter


class TikTokYtDlpAdapter(SourceAdapter):
    """
    Adapter tải video TikTok không watermark đa tầng:
    - Tầng 1: Direct High-Speed API (TikWM) - Không bị chặn bởi bot protection, tốc độ cao.
    - Tầng 2: Dự phòng qua yt-dlp với Custom User-Agent.
    """

    def __init__(self):
        self._user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        self._base_ytdlp_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "socket_timeout": 25,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            },
            "extractor_args": {
                "tiktok": {
                    "api_hostname": "api22-normal-c-useast1a.tiktokv.com",
                    "app_version": "34.1.2",
                    "manifest_app_version": "34.1.2",
                }
            },
        }

    def _clean_url(self, url: str) -> str:
        """Làm sạch URL TikTok."""
        return url.strip().split("?")[0] if "tiktok.com" in url else url.strip()

    def _fetch_tikwm_data(self, url: str) -> Optional[Dict[str, Any]]:
        """Gọi API TikWM với cơ chế Retry & Jitter chống nghẽn đa luồng."""
        clean_url = self._clean_url(url)
        endpoints = [
            "https://www.tikwm.com/api/",
            "https://tikwm.com/api/",
        ]
        headers = {"User-Agent": self._user_agent}

        for attempt in range(3):
            for api_url in endpoints:
                try:
                    with httpx.Client(timeout=20.0) as client:
                        # Thử GET trước
                        res = client.get(api_url, params={"url": clean_url, "hd": 1}, headers=headers)
                        if res.status_code == 200:
                            json_data = res.json()
                            if json_data.get("code") == 0 and "data" in json_data:
                                return json_data["data"]
                        
                        # Thử POST dự phòng
                        res_post = client.post(api_url, data={"url": clean_url, "hd": 1}, headers=headers)
                        if res_post.status_code == 200:
                            json_data = res_post.json()
                            if json_data.get("code") == 0 and "data" in json_data:
                                return json_data["data"]
                except Exception as e:
                    logger.debug(f"[TikWM] Lỗi thử {api_url}: {e}")
            
            # Giãn cách ngẫu nhiên trước khi retry
            time.sleep(random.uniform(0.5, 1.5))

        # Tầng dự phòng: Lovetik API
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post("https://lovetik.com/api/ajax/search", data={"query": clean_url}, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    links = data.get("links") or []
                    play_url = None
                    for l in links:
                        if l.get("a") and "watermark" not in l.get("t", "").lower():
                            play_url = l.get("a")
                            break
                    if not play_url and links:
                        play_url = links[0].get("a")

                    if play_url:
                        return {
                            "id": data.get("vid") or clean_url.split("/")[-1],
                            "title": data.get("desc") or "",
                            "duration": 0.0,
                            "play": play_url,
                            "hdplay": play_url,
                            "author": {"unique_id": data.get("author", ""), "nickname": data.get("author_name", "")},
                        }
        except Exception as e:
            logger.debug(f"[LoveTik Fallback] Lỗi: {e}")

        return None

    def extract_metadata(self, source_url: str) -> SourceVideo:
        """Trích xuất metadata video từ TikTok."""
        url = self._clean_url(source_url)
        logger.debug(f"[TikTok] Đang trích xuất metadata từ {url}...")

        # 1. Thử qua TikWM API & Fallbacks trước
        tikwm_data = self._fetch_tikwm_data(url)
        if tikwm_data:
            v_id = str(tikwm_data.get("id") or "")
            title = tikwm_data.get("title") or ""
            duration = float(tikwm_data.get("duration") or 0.0)
            author = tikwm_data.get("author", {})
            creator_id = str(author.get("unique_id") or "")
            creator_name = str(author.get("nickname") or "")
            tags = re.findall(r"#(\w+)", title)

            return SourceVideo(
                provider="tiktok",
                video_id=v_id or url.split("/")[-1],
                source_url=url,
                title=title,
                tags=tags,
                creator_id=creator_id,
                creator_name=creator_name,
                duration=duration,
                width=tikwm_data.get("size"),
            )

        # 2. Dự phòng qua yt-dlp với Mobile Extractor
        logger.debug("[TikTok] Thử dự phòng qua yt-dlp...")
        opts = {
            **self._base_ytdlp_opts,
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise SourceNotFoundError(f"Không thể trích xuất thông tin video từ {url}")

                video_id = str(info.get("id") or info.get("display_id") or "")
                title = info.get("title") or info.get("description") or ""
                tags = info.get("tags") or []
                creator_id = info.get("uploader_id") or info.get("uploader") or ""
                creator_name = info.get("uploader") or ""
                duration = float(info.get("duration") or 0.0)

                if not tags and title:
                    tags = re.findall(r"#(\w+)", title)

                return SourceVideo(
                    provider="tiktok",
                    video_id=video_id,
                    source_url=url,
                    title=title,
                    tags=tags,
                    creator_id=creator_id,
                    creator_name=creator_name,
                    duration=duration,
                    width=info.get("width"),
                    height=info.get("height"),
                )
        except yt_dlp.utils.DownloadError as e:
            err_str = str(e)
            if "Video unavailable" in err_str or "private" in err_str or "not found" in err_str:
                raise SourceNotFoundError(f"Video TikTok không tồn tại hoặc đã bị ẩn: {err_str}")
            
            # Fallback nhẹ: nếu cả 2 đều không lấy được metadata chi tiết nhưng có URL, tạo metadata sơ bộ
            vid_match = re.search(r'/video/(\d+)', url)
            if vid_match:
                fallback_id = vid_match.group(1)
                return SourceVideo(
                    provider="tiktok",
                    video_id=fallback_id,
                    source_url=url,
                    title="Video TikTok",
                    tags=[],
                    creator_id="",
                    creator_name="",
                    duration=0.0,
                )
            raise SourceExtractionError(f"Lỗi khi trích xuất TikTok: {err_str}")
        except Exception as e:
            raise SourceExtractionError(f"Lỗi không xác định khi đọc TikTok: {e}")

    def download_video(self, source_url: str, output_path: Path) -> SourceVideo:
        """Tải video MP4 chất lượng cao nhất không có watermark."""
        url = self._clean_url(source_url)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = output_path.with_suffix(".part")

        # 1. Thử tải trực tiếp qua stream TikWM
        tikwm_data = self._fetch_tikwm_data(url)
        if tikwm_data:
            # Chọn URL HD nếu có, không thì lấy play URL tiêu chuẩn
            download_url = (
                tikwm_data.get("hdplay")
                or tikwm_data.get("play")
                or tikwm_data.get("wmplay")
            )
            if download_url:
                try:
                    logger.info(f"[TikTok] Đang stream tải video MP4 từ CDN tốc độ cao...")
                    headers = {"User-Agent": self._user_agent, "Referer": "https://www.tiktok.com/"}
                    
                    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                        with client.stream("GET", download_url, headers=headers) as res:
                            if res.status_code == 200:
                                with open(part_path, "wb", buffering=4*1024*1024) as f:
                                    for chunk in res.iter_bytes(chunk_size=1048576):  # 1 MB chunks
                                        f.write(chunk)

                                if part_path.exists() and part_path.stat().st_size > 0:
                                    part_path.replace(output_path)
                                    file_size = output_path.stat().st_size

                                    title = tikwm_data.get("title") or ""
                                    tags = re.findall(r"#(\w+)", title)
                                    author = tikwm_data.get("author", {})

                                    logger.info(f"[green]✔ Tải video thành công ({file_size / (1024*1024):.2f} MB)![/green]")
                                    return SourceVideo(
                                        provider="tiktok",
                                        video_id=str(tikwm_data.get("id") or url.split("/")[-1]),
                                        source_url=url,
                                        title=title,
                                        tags=tags,
                                        creator_id=str(author.get("unique_id") or ""),
                                        creator_name=str(author.get("nickname") or ""),
                                        duration=float(tikwm_data.get("duration") or 0.0),
                                        file_size_bytes=file_size,
                                        file_path=output_path,
                                    )
                except Exception as e:
                    logger.warning(f"[TikTok] Stream TikWM lỗi ({e}), chuyển sang dự phòng yt-dlp...")

        # 2. Dự phòng qua yt-dlp
        ydl_opts = {
            **self._base_ytdlp_opts,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": str(part_path),
            "overwrites": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise SourceNotFoundError(f"Không thể tải video từ {url}")

                downloaded_file = None
                if part_path.exists():
                    downloaded_file = part_path
                else:
                    candidates = list(output_path.parent.glob(f"{part_path.stem}*"))
                    if candidates:
                        downloaded_file = candidates[0]

                if not downloaded_file or not downloaded_file.exists():
                    raise SourceExtractionError("Không tìm thấy file video đầu ra sau khi tải.")

                downloaded_file.replace(output_path)
                file_size = output_path.stat().st_size

                video_id = str(info.get("id") or info.get("display_id") or "")
                title = info.get("title") or info.get("description") or ""
                tags = info.get("tags") or []
                if not tags and title:
                    tags = re.findall(r"#(\w+)", title)

                return SourceVideo(
                    provider="tiktok",
                    video_id=video_id,
                    source_url=url,
                    title=title,
                    tags=tags,
                    creator_id=info.get("uploader_id") or info.get("uploader") or "",
                    creator_name=info.get("uploader") or "",
                    duration=float(info.get("duration") or 0.0),
                    file_size_bytes=file_size,
                    file_path=output_path,
                )
        except Exception as e:
            raise SourceExtractionError(f"Lỗi khi tải video TikTok: {e}")

    def list_channel_videos(self, channel_url: str, limit: int = 5) -> List[SourceVideo]:
        """Lấy danh sách các video mới nhất từ trang cá nhân Creator."""
        opts = {
            **self._base_ytdlp_opts,
            "extract_flat": True,
            "playlistend": limit,
            "skip_download": True,
        }

        videos = []
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
                entries = info.get("entries") or []

                for entry in entries:
                    if not entry:
                        continue
                    v_id = str(entry.get("id") or "")
                    v_url = entry.get("url") or f"https://www.tiktok.com/@{entry.get('uploader_id', 'user')}/video/{v_id}"
                    videos.append(
                        SourceVideo(
                            provider="tiktok",
                            video_id=v_id,
                            source_url=v_url,
                            title=entry.get("title") or "",
                            duration=float(entry.get("duration") or 0.0),
                            creator_id=entry.get("uploader_id") or "",
                        )
                    )
            return videos
        except Exception as e:
            logger.error(f"[TikTok] Lỗi khi quét kênh {channel_url}: {e}")
            return []
