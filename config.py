# ============================================================
# CẤU HÌNH TOOL QUÉT LINK TIKTOK & XUẤT EXCEL
# ============================================================

# Thư mục mặc định để lưu file Excel xuất ra
DEFAULT_EXPORT_DIR = "exports"

# Tên cột trong file Excel (format |link|)
EXCEL_COLUMN_NAME = "link"

# Giới hạn số lượng video lấy mặc định (0 = lấy tất cả)
DEFAULT_LIMIT = 0

# Đường dẫn file cookies tĩnh nếu cần vượt chặn của TikTok (định dạng Netscape cookies.txt)
COOKIES_PATH = "data/cookies.txt"

# Chạy trình duyệt ẩn (True) hay hiện cửa sổ để xem/giải captcha (False)
HEADLESS = False

# Đường dẫn lưu file log
LOG_PATH = "data/log.txt"

# Cơ sở dữ liệu hash video chống trùng
POSTED_HASH_DB_PATH = "data/posted_hashes.json"

# Mẫu Caption tạo tự động
CAPTION_TEMPLATES = [
    "{title} #trending #viral #fyp",
    "Xem ngay: {title} #videohot #tiktokvn",
    "{title} cực hay đừng bỏ lỡ! #shorts #viral",
    "Khám phá {title} cùng chúng mình nhé! #trend",
]

# Danh sách hashtag đề xuất
HASHTAG_POOL = [
    "#fyp", "#trending", "#viral", "#xuhuong", "#tiktokvn",
    "#review", "#hot", "#shorts", "#funny", "#congnghe"
]
