import os
import sys
import json
import re
import html
import urllib.parse
import subprocess
import time
from typing import List, Dict, Tuple

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

def is_valid_tiktok_video(url: str) -> bool:
    """Kiểm tra link đúng chuẩn video TikTok 100% (@username/video/19_chữ_số)."""
    if not url:
        return False
    clean = url.split("?")[0].strip()
    return bool(re.search(r'https?://(?:www\.)?tiktok\.com/@[a-zA-Z0-9_.-]+/video/\d{15,22}$', clean))


class TikTokSearchEngine:
    """
    Hệ thống tìm kiếm Video TikTok kép:
    1. Google/Yahoo Indexer (Dùng curl_cffi vượt Captcha - Không bao giờ bị chặn captcha TikTok).
    2. Headed Browser Automation (Mở cửa sổ Chrome thật - nếu dính Captcha thì người dùng chỉ cần kéo trượt 1 giây là xong).
    """

    @classmethod
    def search_via_google_index(cls, keyword: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Tìm kiếm video TikTok qua Google Index bằng curl_cffi.
        Ưu điểm: KHÔNG BAO GIỜ bị Captcha của TikTok, tốc độ cực nhanh (1 giây).
        """
        try:
            from curl_cffi import requests
        except ImportError:
            import urllib.request as requests_fallback

        videos = []
        seen_ids = set()

        queries = [
            f'site:tiktok.com/video "{keyword}"',
            f'site:tiktok.com/@* video {keyword}',
            f'site:tiktok.com {keyword}'
        ]

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        for q in queries:
            if len(videos) >= limit:
                break

            url = f"https://www.google.com/search?q={urllib.parse.quote(q)}&hl=vi&num=30"

            try:
                try:
                    from curl_cffi import requests
                    resp = requests.get(url, headers=headers, impersonate="chrome124", timeout=15)
                    page_html = resp.text
                except Exception:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        page_html = resp.read().decode("utf-8", errors="ignore")

                # Tìm tất cả link TikTok thật trong HTML Google
                # Định dạng URL trên Google có thể là trực tiếp hoặc qua url?q=
                raw_urls = re.findall(r'https?://(?:www\.)?tiktok\.com/@[a-zA-Z0-9_.-]+/video/\d{15,22}', page_html)
                
                # Tìm kèm caption/title tương ứng
                # Tách từng khối kết quả
                blocks = re.findall(r'<div class="[^"]*MjjYud[^"]*"[^>]*>(.*?)</div></div></div>', page_html, re.DOTALL)
                if not blocks:
                    blocks = re.findall(r'<div class="[^"]*g[^"]*"[^>]*>(.*?)</div></div>', page_html, re.DOTALL)

                for block in blocks:
                    link_match = re.search(r'href="([^"]*tiktok\.com/@[a-zA-Z0-9_.-]+/video/\d{15,22}[^"]*)"', block)
                    if link_match:
                        raw_link = link_match.group(1)
                        clean_url = raw_link.split("?")[0].strip()
                        vid_match = re.search(r'/video/(\d+)', clean_url)
                        if not vid_match:
                            continue
                        
                        vid = vid_match.group(1)
                        if vid in seen_ids:
                            continue
                        seen_ids.add(vid)

                        # Tìm title/caption
                        title_match = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
                        snippet_match = re.search(r'<div class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
                        
                        cap = ""
                        if snippet_match:
                            cap = re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip()
                        elif title_match:
                            cap = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                        
                        if not cap:
                            cap = f"Video TikTok về {keyword}"

                        cap = html.unescape(cap).replace("\r\n", " ").replace("\n", " ").strip()

                        if is_valid_tiktok_video(clean_url):
                            videos.append({
                                "url": clean_url,
                                "desc": cap
                            })

                        if len(videos) >= limit:
                            break

                # Nếu blocks chưa bóc tách đủ, lấy trực tiếp từ raw_urls
                for u in raw_urls:
                    clean_url = u.split("?")[0].strip()
                    vid_match = re.search(r'/video/(\d+)', clean_url)
                    if vid_match:
                        vid = vid_match.group(1)
                        if vid not in seen_ids and is_valid_tiktok_video(clean_url):
                            seen_ids.add(vid)
                            videos.append({
                                "url": clean_url,
                                "desc": f"Video TikTok xu hướng #{keyword}"
                            })
                            if len(videos) >= limit:
                                break

            except Exception:
                continue

        return videos

    @classmethod
    def search_via_headed_browser(cls, keyword: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Mở cửa sổ Chrome thật (Headed Mode).
        Nếu TikTok hiện Captcha, người dùng kéo thanh trượt giải Captcha, tool sẽ tự động bóc tách video ngay!
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
            from playwright.sync_api import sync_playwright

        videos = []
        seen_ids = set()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=False, # Hiện cửa sổ thật để người dùng kéo Captcha nếu có
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--start-maximized"
                    ]
                )
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    locale="vi-VN"
                )
                page = context.new_page()

                # Bắt gói tin API ngầm
                def handle_response(response):
                    try:
                        if "api/search" in response.url and response.status == 200:
                            data = response.json()
                            for it in (data.get("data") or []):
                                item = it.get("item") or it
                                v_id = str(item.get("id") or item.get("video_id") or "")
                                if v_id and v_id not in seen_ids:
                                    seen_ids.add(v_id)
                                    author = (item.get("author") or {}).get("uniqueId") or "user"
                                    desc = (item.get("desc") or item.get("title") or f"Video #{keyword}").replace("\r\n", " ").replace("\n", " ").strip()
                                    url = f"https://www.tiktok.com/@{author}/video/{v_id}"
                                    if is_valid_tiktok_video(url):
                                        videos.append({"url": url, "desc": desc})
                    except Exception:
                        pass

                page.on("response", handle_response)

                search_url = f"https://www.tiktok.com/search?q={urllib.parse.quote(keyword)}"
                page.goto(search_url, timeout=45000)

                # Chờ người dùng giải Captcha (nếu có) hoặc chờ trang tải video (tối đa 15 giây)
                for _ in range(15):
                    if len(videos) >= limit:
                        break
                    
                    # Kiểm tra xem đã có video trên DOM chưa
                    anchors = page.locator('a[href*="/video/"]').evaluate_all("""
                        elements => elements.map(a => ({
                            href: a.href,
                            text: a.innerText || a.getAttribute('title') || ''
                        }))
                    """)
                    for a in anchors:
                        href = a.get("href", "").split("?")[0].strip()
                        vid_m = re.search(r'/video/(\d+)', href)
                        if vid_m:
                            vid = vid_m.group(1)
                            if vid not in seen_ids and is_valid_tiktok_video(href):
                                seen_ids.add(vid)
                                cap = (a.get("text") or f"Video #{keyword}").replace("\r\n", " ").replace("\n", " ").strip()
                                videos.append({"url": href, "desc": cap})
                                if len(videos) >= limit:
                                    break

                    if len(videos) >= limit:
                        break

                    page.evaluate("window.scrollBy(0, 800)")
                    time.sleep(1.5)

                browser.close()
        except Exception:
            pass

        return videos[:limit]

    @classmethod
    def search(cls, keyword: str, limit: int = 10, mode: str = "auto") -> Tuple[List[Dict[str, str]], str]:
        """
        Tìm kiếm video TikTok:
        - Mode 'fast': Dùng Google Indexer (Vượt 100% Captcha TikTok, siêu nhanh)
        - Mode 'browser': Mở trình duyệt Chrome thật (Có thể tự giải captcha nếu cần)
        - Mode 'auto': Thử Fast trước, nếu không có mới mở Browser.
        """
        if mode == "browser":
            videos = cls.search_via_headed_browser(keyword, limit)
            return videos, "Trình duyệt Chrome (Headed)"

        # Mặc định thử qua Google Indexer trước (tránh 100% Captcha)
        videos = cls.search_via_google_index(keyword, limit)
        if videos and len(videos) > 0:
            return videos, "Google Video Index (Không Captcha)"

        # Nếu không ra thì mở trình duyệt Chrome
        videos = cls.search_via_headed_browser(keyword, limit)
        if videos and len(videos) > 0:
            return videos, "Trình duyệt Chrome"

        return [], "Không tìm thấy"
