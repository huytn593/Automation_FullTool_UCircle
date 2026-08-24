import os
import re
import time
import random
from typing import List, Dict, Any, Optional, Set
from urllib.parse import urlsplit, urlunsplit
import httpx
import yt_dlp

from tollcal.observability.logging import logger


class TikTokChannelScanner:
    """
    Bộ quét toàn bộ video từ kênh / trang cá nhân TikTok.
    Hỗ trợ 3 cơ chế:
    1. Direct API (TikWM User Feed) - Tốc độ cực nhanh (vài giây quét hàng trăm video, không tốn tài nguyên).
    2. Yt-Dlp Flat Playlist (Dự phòng qua metadata scraper).
    3. Headless Browser (Playwright infinite scroll mô phỏng cuộn trang giống TikTokLinkExtractor).
    """

    def __init__(self):
        self._user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

    def extract_username(self, channel_input: str) -> str:
        """Trích xuất username chuẩn (bỏ @ và URL) từ chuỗi người dùng nhập."""
        cleaned = channel_input.strip()
        
        # Nếu là link ngắn vt.tiktok.com, resolve redirect trước
        if "vt.tiktok.com" in cleaned or "/t/" in cleaned:
            try:
                with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                    res = client.head(cleaned)
                    cleaned = str(res.url)
            except Exception:
                pass

        # Trích xuất @username từ URL
        match = re.search(r"@([a-zA-Z0-9_.-]+)", cleaned)
        if match:
            return match.group(1)

        # Nếu người dùng chỉ gõ @username hoặc username
        cleaned = cleaned.lstrip("@").split("/")[0].split("?")[0].strip()
        return cleaned

    def scan_via_api(self, username: str, max_videos: int = 100, max_duration: Optional[float] = 120.0) -> List[Dict[str, Any]]:
        """
        Quét danh sách video của Creator qua TikWM User Posts API.
        Hỗ trợ lọc video theo thời lượng tối đa (mặc định <= 120s / 2 phút).
        """
        api_url = "https://www.tikwm.com/api/user/posts"
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
        }

        videos = []
        seen_ids: Set[str] = set()
        cursor = "0"
        has_more = True
        page_num = 1
        max_pages = 10

        logger.info(f"[TikTok Scanner API] Bắt đầu quét kênh @{username} (Thời lượng <= {max_duration}s)...")

        try:
            with httpx.Client(timeout=20.0) as client:
                while has_more and len(videos) < max_videos and page_num <= max_pages:
                    params = {
                        "unique_id": username,
                        "count": 30,
                        "cursor": cursor,
                    }
                    res = client.get(api_url, params=params, headers=headers)
                    if res.status_code != 200:
                        logger.warning(f"[TikTok Scanner API] HTTP {res.status_code} khi quét page {page_num}")
                        break

                    data = res.json()
                    if data.get("code") != 0 or "data" not in data:
                        logger.debug(f"[TikTok Scanner API] Message: {data.get('msg')}")
                        break

                    feed_data = data["data"]
                    raw_videos = feed_data.get("videos") or []
                    if not raw_videos:
                        break

                    for v in raw_videos:
                        v_id = str(v.get("video_id") or v.get("id") or "")
                        if not v_id or v_id in seen_ids:
                            continue

                        dur = float(v.get("duration") or 0.0)
                        # Lọc thời lượng nếu có cấu hình max_duration
                        if max_duration and max_duration > 0 and dur > 0 and dur > max_duration:
                            continue

                        seen_ids.add(v_id)
                        title = v.get("title") or ""
                        tags = re.findall(r"#(\w+)", title)
                        video_url = f"https://www.tiktok.com/@{username}/video/{v_id}"
                        
                        videos.append({
                            "video_id": v_id,
                            "url": video_url,
                            "title": title,
                            "tags": tags,
                            "duration": dur,
                            "cover": v.get("cover") or v.get("origin_cover") or "",
                            "views": v.get("play_count") or 0,
                            "likes": v.get("digg_count") or 0,
                            "created_at": v.get("create_time"),
                        })

                        if len(videos) >= max_videos:
                            break

                    has_more = feed_data.get("hasMore", False)
                    cursor = str(feed_data.get("cursor", "0"))
                    page_num += 1
                    
                    if has_more and len(videos) < max_videos:
                        time.sleep(0.3)  # Giãn cách nhẹ chống rate limit

        except Exception as e:
            logger.warning(f"[TikTok Scanner API] Lỗi trong quá trình quét API: {e}")

        logger.info(f"[TikTok Scanner API] Đã tìm thấy {len(videos)} video từ kênh @{username}")
        return videos

    def scan_via_ytdlp(self, channel_url: str, max_videos: int = 100, max_duration: Optional[float] = 120.0) -> List[Dict[str, Any]]:
        """Quét video của kênh qua yt-dlp Flat Playlist."""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlistend": max_videos,
            "socket_timeout": 20,
            "http_headers": {
                "User-Agent": self._user_agent,
                "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            },
        }

        videos = []
        try:
            logger.info(f"[TikTok Scanner yt-dlp] Đang quét playlist {channel_url}...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
                entries = info.get("entries") or []

                for entry in entries:
                    if not entry:
                        continue
                    v_id = str(entry.get("id") or "")
                    v_url = entry.get("url") or (
                        f"https://www.tiktok.com/@{entry.get('uploader_id', 'user')}/video/{v_id}"
                        if v_id else ""
                    )
                    if not v_url or "tiktok.com" not in v_url:
                        continue

                    dur = float(entry.get("duration") or 0.0)
                    if max_duration and max_duration > 0 and dur > 0 and dur > max_duration:
                        continue

                    title = entry.get("title") or ""
                    tags = re.findall(r"#(\w+)", title)
                    videos.append({
                        "video_id": v_id,
                        "url": v_url,
                        "title": title,
                        "tags": tags,
                        "duration": dur,
                        "cover": entry.get("thumbnail") or "",
                        "views": entry.get("view_count") or 0,
                        "likes": entry.get("like_count") or 0,
                    })
        except Exception as e:
            logger.warning(f"[TikTok Scanner yt-dlp] Lỗi quét: {e}")

        return videos

    def scan_via_browser(self, channel_url: str, max_videos: int = 100, headless: bool = True) -> List[Dict[str, Any]]:
        """
        Quét kênh TikTok bằng trình duyệt Playwright mô phỏng cuộn trang vô tận (Infinite Scroll).
        Tương tự cơ chế của TikTokLinkExtractor.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("[TikTok Scanner Browser] Chưa cài đặt thư viện playwright.")
            return []

        videos = []
        seen_links: Set[str] = set()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    locale="vi-VN",
                    user_agent=self._user_agent,
                )
                page = context.new_page()
                logger.info(f"[TikTok Scanner Browser] Đang mở trang {channel_url}...")
                page.goto(channel_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)

                no_change_rounds = 0
                max_no_change = 4

                while len(videos) < max_videos and no_change_rounds < max_no_change:
                    # Lấy tất cả thẻ <a> có href chứa /video/
                    raw_links = page.locator("a").evaluate_all("""
                        elements => elements
                            .map(a => a.href)
                            .filter(href => href && href.includes('tiktok.com') && href.includes('/video/'))
                    """)

                    prev_count = len(videos)
                    for link in raw_links:
                        # Clean link
                        parts = urlsplit(link)
                        clean_link = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
                        if clean_link not in seen_links:
                            seen_links.add(clean_link)
                            vid_match = re.search(r'/video/(\d+)', clean_link)
                            vid = vid_match.group(1) if vid_match else ""
                            videos.append({
                                "video_id": vid,
                                "url": clean_link,
                                "title": "",
                                "tags": [],
                                "duration": 0.0,
                                "cover": "",
                            })
                            if len(videos) >= max_videos:
                                break

                    if len(videos) > prev_count:
                        no_change_rounds = 0
                    else:
                        no_change_rounds += 1

                    # Cuộn chuột xuống dưới
                    page.mouse.wheel(0, 1200)
                    delay = random.uniform(1.2, 2.0)
                    page.wait_for_timeout(int(delay * 1000))

                context.close()
                browser.close()
        except Exception as e:
            logger.warning(f"[TikTok Scanner Browser] Lỗi chạy trình duyệt: {e}")

        return videos

    def _normalize_search_keyword(self, text: str) -> str:
        """Chuyển đổi từ khóa có dấu sang không dấu để dự phòng tìm kiếm."""
        import unicodedata
        nfkd = unicodedata.normalize('NFKD', text)
        return ''.join([c for c in nfkd if not unicodedata.combining(c)])

    def search_via_api(self, keywords: str, max_videos: int = 100, max_duration: Optional[float] = 120.0) -> List[Dict[str, Any]]:
        """
        Tìm kiếm video TikTok theo từ khóa/chủ đề qua Search Feed API (Không bao giờ dính Captcha).
        Hỗ trợ lọc thời lượng tối đa (mặc định <= 120s / 2 phút).
        """
        api_endpoints = [
            "https://www.tikwm.com/api/feed/search",
            "https://tikwm.com/api/feed/search",
        ]
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.tikwm.com",
            "Referer": "https://www.tikwm.com/",
        }

        clean_kw = keywords.lstrip("#").strip()
        kw_candidates = [clean_kw]
        no_accent = self._normalize_search_keyword(clean_kw)
        if no_accent.lower() != clean_kw.lower():
            kw_candidates.append(no_accent)

        for kw in kw_candidates:
            for api_url in api_endpoints:
                videos = []
                seen_ids: Set[str] = set()
                cursor = "0"
                has_more = True

                logger.info(f"[TikTok Search API] Thử tìm kiếm '{kw}' qua {api_url} (<= {max_duration}s)...")

                try:
                    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                        while has_more and len(videos) < max_videos:
                            payload = {
                                "keywords": kw,
                                "count": 30,
                                "cursor": cursor,
                                "web": 1,
                                "hd": 1,
                            }
                            # Thử POST trước (TikWM search API ưu tiên form data)
                            res = client.post(api_url, data=payload, headers=headers)
                            data = {}
                            try:
                                data = res.json()
                            except Exception:
                                pass

                            if res.status_code != 200 or data.get("code") != 0:
                                # Thử GET nếu POST không được
                                res = client.get(api_url, params=payload, headers=headers)
                                try:
                                    data = res.json()
                                except Exception:
                                    data = {}

                            if res.status_code != 200 or data.get("code") != 0 or "data" not in data:
                                break

                            feed_data = data.get("data")
                            raw_videos = []
                            if isinstance(feed_data, list):
                                raw_videos = feed_data
                            elif isinstance(feed_data, dict):
                                raw_videos = feed_data.get("videos") or []

                            if not raw_videos:
                                break

                            for v in raw_videos:
                                if not isinstance(v, dict):
                                    continue
                                v_id = str(v.get("video_id") or v.get("id") or "")
                                if not v_id or v_id in seen_ids:
                                    continue

                                dur = float(v.get("duration") or 0.0)
                                if max_duration and max_duration > 0 and dur > 0 and dur > max_duration:
                                    continue

                                seen_ids.add(v_id)
                                title = v.get("title") or ""
                                tags = re.findall(r"#(\w+)", title)
                                author = v.get("author") or {}
                                if isinstance(author, dict):
                                    username = author.get("unique_id") or "user"
                                else:
                                    username = str(author)
                                video_url = f"https://www.tiktok.com/@{username}/video/{v_id}"

                                videos.append({
                                    "video_id": v_id,
                                    "url": video_url,
                                    "title": title,
                                    "tags": tags,
                                    "duration": dur,
                                    "cover": v.get("cover") or v.get("origin_cover") or "",
                                    "views": v.get("play_count") or 0,
                                    "likes": v.get("digg_count") or 0,
                                    "creator_id": username,
                                    "created_at": v.get("create_time"),
                                })

                                if len(videos) >= max_videos:
                                    break

                            if isinstance(feed_data, dict):
                                has_more = feed_data.get("hasMore", False)
                                cursor = str(feed_data.get("cursor", "0"))
                            else:
                                has_more = False

                            if has_more and len(videos) < max_videos:
                                time.sleep(0.3)

                except Exception as e:
                    logger.warning(f"[TikTok Search API] Lỗi tìm kiếm '{kw}': {e}")

                if videos:
                    logger.info(f"[TikTok Search API] Tìm thấy {len(videos)} video cho từ khóa '{kw}'")
                    return videos

        return []

    def search_via_tag_api(self, tag: str, max_videos: int = 100, max_duration: Optional[float] = 120.0) -> List[Dict[str, Any]]:
        """Tìm kiếm video qua Hashtag/Challenge API."""
        clean_tag = tag.lstrip("#").replace(" ", "").strip()
        api_endpoints = [
            "https://www.tikwm.com/api/challenge/posts",
            "https://tikwm.com/api/challenge/posts",
        ]
        headers = {"User-Agent": self._user_agent}
        videos = []
        for api_url in api_endpoints:
            try:
                with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                    res = client.get(api_url, params={"challenge_name": clean_tag, "count": 30, "cursor": 0}, headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        if data.get("code") == 0 and "data" in data:
                            feed_data = data["data"]
                            raw = feed_data.get("videos") if isinstance(feed_data, dict) else feed_data
                            for v in (raw or []):
                                if not isinstance(v, dict):
                                    continue
                                v_id = str(v.get("video_id") or v.get("id") or "")
                                if v_id:
                                    dur = float(v.get("duration") or 0.0)
                                    if max_duration and max_duration > 0 and dur > 0 and dur > max_duration:
                                        continue
                                    author = v.get("author") or {}
                                    username = author.get("unique_id") if isinstance(author, dict) else str(author)
                                    title = v.get("title") or ""
                                    videos.append({
                                        "video_id": v_id,
                                        "url": f"https://www.tiktok.com/@{username}/video/{v_id}",
                                        "title": title,
                                        "tags": re.findall(r"#(\w+)", title),
                                        "duration": dur,
                                        "cover": v.get("cover") or "",
                                        "views": v.get("play_count") or 0,
                                        "creator_id": username,
                                    })
                            if videos:
                                break
            except Exception as e:
                logger.debug(f"[TikTok Tag API] Lỗi {api_url}: {e}")
        return videos

    def search_via_web_search(self, keywords: str, max_videos: int = 50) -> List[Dict[str, Any]]:
        """
        Tìm kiếm video TikTok qua Web Search Engine không bao giờ dính Captcha.
        Trích xuất trực tiếp các video TikTok phù hợp nhất với từ khóa.
        """
        videos = []
        seen_ids: Set[str] = set()
        clean_kw = keywords.lstrip("#").strip()
        
        queries = [
            f'site:tiktok.com video "{clean_kw}"',
            f'site:tiktok.com "{clean_kw}"',
            f'tiktok "{clean_kw}"',
        ]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                for q in queries:
                    if len(videos) >= max_videos:
                        break
                    
                    try:
                        res = client.post("https://html.duckduckgo.com/html/", data={"q": q}, headers=headers)
                        if res.status_code == 200:
                            html_text = res.text
                            raw_links = re.findall(r'(https?://(?:www\.)?tiktok\.com/@[a-zA-Z0-9_.-]+/video/(\d+))', html_text)
                            for full_url, v_id in raw_links:
                                if v_id not in seen_ids:
                                    seen_ids.add(v_id)
                                    user_match = re.search(r'tiktok\.com/@([a-zA-Z0-9_.-]+)/video/', full_url)
                                    username = user_match.group(1) if user_match else "user"
                                    
                                    videos.append({
                                        "video_id": v_id,
                                        "url": full_url,
                                        "title": f"TikTok video #{v_id} ({clean_kw})",
                                        "tags": [clean_kw.replace(" ", "")],
                                        "duration": 0.0,
                                        "cover": "",
                                        "views": 0,
                                        "likes": 0,
                                        "creator_id": username,
                                        "created_at": None,
                                    })
                                    if len(videos) >= max_videos:
                                        break
                    except Exception as sub_e:
                        logger.debug(f"[Web Search Scraper] Lỗi query '{q}': {sub_e}")

        except Exception as e:
            logger.warning(f"[Web Search Scraper] Lỗi tổng thể: {e}")

        if videos:
            logger.info(f"[Web Search Scraper] Tìm thấy {len(videos)} video TikTok cho từ khóa '{clean_kw}'")
        return videos

    def search_via_browser(self, keywords: str, max_videos: int = 100, headless: bool = True) -> List[Dict[str, Any]]:
        """Tìm kiếm video TikTok qua giao diện tìm kiếm TikTok web."""
        import urllib.parse
        search_url = f"https://www.tiktok.com/search?q={urllib.parse.quote(keywords)}"
        return self.scan_via_browser(search_url, max_videos=max_videos, headless=headless)

    def search(self, keywords: str, max_videos: int = 100, method: str = "auto", max_duration: Optional[float] = 120.0) -> List[Dict[str, Any]]:
        """
        Tìm kiếm video theo từ khóa (Keyword Search) với 5 tầng fallback và bộ lọc thời lượng:
        - Tầng 1: Search Feed API (TikWM)
        - Tầng 2: Hashtag / Challenge API
        - Tầng 3: Web Search Engine (DuckDuckGo Scraper - 0 Captcha)
        - Tầng 4: yt-dlp Tag Flat Playlist
        - Tầng 5: Playwright Browser
        """
        if method == "browser":
            return self.search_via_browser(keywords, max_videos=max_videos)
        
        # 1. Thử Search API
        results = self.search_via_api(keywords, max_videos=max_videos, max_duration=max_duration)
        if results:
            return results
        
        # 2. Thử Tag API (với cả tag gốc và tag bỏ khoảng trắng)
        tag_candidate = keywords.lstrip("#").replace(" ", "").strip()
        results = self.search_via_tag_api(tag_candidate, max_videos=max_videos, max_duration=max_duration)
        if results:
            return results

        # 3. Thử Web Search Scraper (DuckDuckGo)
        results = self.search_via_web_search(keywords, max_videos=max_videos)
        if results:
            return results

        # 4. Thử Tag qua yt-dlp
        tag_url = f"https://www.tiktok.com/tag/{tag_candidate}"
        results = self.scan_via_ytdlp(tag_url, max_videos=max_videos, max_duration=max_duration)
        if results:
            return results

        # 5. Fallback cuối: Browser
        return self.search_via_browser(keywords, max_videos=max_videos)

    def scan(self, channel_input: str, max_videos: int = 100, method: str = "auto", max_duration: Optional[float] = 120.0) -> List[Dict[str, Any]]:
        """
        Quét kênh TikTok hoặc từ khóa với cơ chế tự động chọn giải pháp tối ưu nhất:
        - Tầng 1: API (Cực nhanh, trả về đầy đủ title, hashtag, duration, cover)
        - Tầng 2: yt-dlp Flat Playlist (Dự phòng)
        - Tầng 3: Playwright Browser (Dự phòng nâng cao)
        """
        username = self.extract_username(channel_input)
        channel_url = f"https://www.tiktok.com/@{username}" if username else channel_input

        if method == "browser":
            return self.scan_via_browser(channel_url, max_videos=max_videos)
        elif method == "ytdlp":
            return self.scan_via_ytdlp(channel_url, max_videos=max_videos, max_duration=max_duration)

        # Mặc định auto: Thử API trước
        if username:
            results = self.scan_via_api(username, max_videos=max_videos, max_duration=max_duration)
            if results:
                return results

        # Dự phòng 1: yt-dlp
        results = self.scan_via_ytdlp(channel_url, max_videos=max_videos, max_duration=max_duration)
        if results:
            return results

        # Dự phòng 2: browser
        return self.scan_via_browser(channel_url, max_videos=max_videos)


channel_scanner = TikTokChannelScanner()


