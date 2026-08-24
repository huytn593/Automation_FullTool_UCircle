import sys
from tiktok_search_core import TikTokSearchEngine

def test(keyword="hài hước", limit=5, mode="fast"):
    print(f"\n===========================================================")
    print(f"  TEST TÌM KIẾM VIDEO TIKTOK: '{keyword}' (Chế độ: {mode})")
    print(f"===========================================================\n")
    
    videos, method = TikTokSearchEngine.search(keyword, limit, mode)
    print(f"🚀 Nguồn lấy dữ liệu: {method}")
    print(f"🎉 TỔNG SỐ VIDEO THẬT: {len(videos)}\n")
    
    if not videos:
        print("❌ Chưa lấy được video. Hãy thử chế độ 'browser' để tự giải Captcha nếu TikTok yêu cầu:")
        print(f"   python test_search.py \"{keyword}\" {limit} browser\n")
        return

    for i, v in enumerate(videos, 1):
        print(f"[{i}] Link   : {v['url']}")
        print(f"    Caption: {v['desc']}\n")

if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "hài hước"
    num = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    m = sys.argv[3] if len(sys.argv) > 3 else "fast"
    test(kw, num, m)
