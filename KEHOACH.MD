# KẾ HOẠCH PHÁT TRIỂN HỆ THỐNG TỰ ĐỘNG HÓA CLONE & ĐỒNG BỘ VIDEO TIKTOK SANG UCIRCLE (WAVEE)

---

## 1. TỔNG QUAN DỰ ÁN (PROJECT OVERVIEW)

* **Mục tiêu**: Xây dựng phần mềm/công cụ tự động hóa quá trình lấy video ngắn từ TikTok (video đơn lẻ hoặc tự động theo dõi toàn bộ kênh của Creator) và đồng bộ đăng tải lên tính năng **Wavee** của mạng xã hội **UCircle** mà không cần thao tác thủ công.
* **Cơ chế vận hành**: Client-Side Automation thông qua HTTP APIs công khai của UCircle và kỹ thuật trích xuất video TikTok không watermark (No-Watermark Extraction).
* **Môi trường triển khai**: Chạy trên máy tính cá nhân (Windows/macOS/Linux) hoặc máy chủ ảo VPS (Ubuntu/Debian) chạy chế độ nền (Background Service / Daemon / Cron).

---

## 2. SƠ ĐỒ KIẾN TRÚC & LUỒNG DỮ LIỆU (ARCHITECTURE & FLOW)

```
                     ┌──────────────────────────────────────────────┐
                     │            NGUỒN DỮ LIỆU (TIKTOK)            │
                     │  - Video URL đơn lẻ                          │
                     │  - Danh sách kênh Creator (Monitor List)     │
                     └──────────────────────┬───────────────────────┘
                                            │
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │       MODULE 1: TIKTOK EXTRACTOR & DL        │
                     │  - Trích xuất link MP4 HD không watermark    │
                     │  - Lấy Metadata: Tiêu đề, Hashtags, Thời lượng│
                     └──────────────────────┬───────────────────────┘
                                            │
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │       MODULE 2: QUẢN LÝ DỮ LIỆU & LỌC        │
                     │  - SQLite Database kiểm tra trùng lặp        │
                     │  - Chuẩn hóa caption (tối đa 2200 ký tự)    │
                     │  - Kiểm tra điều kiện dung lượng & thời lượng│
                     └──────────────────────┬───────────────────────┘
                                            │
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │       MODULE 3: UCIRCLE WAVEE CONNECTOR      │
                     │  1. Đăng nhập Supabase Auth -> Access Token  │
                     │  2. RPC kiểm tra hạn mức (Caps/Quota check)  │
                     │  3. RPC tạo Upload Intent (video_id)         │
                     │  4. Gọi Provision API lấy Signed Upload URL  │
                     │  5. Tải lên tệp video nhị phân (Multipart)   │
                     │  6. Polling trạng thái Encode & Hoàn tất     │
                     └──────────────────────┬───────────────────────┘
                                            │
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │          ĐÍCH ĐẾN: UCIRCLE WAVEE             │
                     │  - Video xuất hiện trên Feed / Wavee Tab     │
                     │  - Tự động gắn Circle ID (nếu có)            │
                     │  - Lưu log lịch sử đồng bộ thành công        │
                     └──────────────────────────────────────────────┘
```

---

## 3. CÁC MODULE CHỨC NĂNG CHI TIẾT (CORE MODULES)

### Module 1: TikTok Scraper & Downloader (`tiktok_engine.py`)
* **Chức năng**:
  * Nhận đầu vào là link video TikTok (dạng `https://vt.tiktok.com/...` hoặc `https://www.tiktok.com/@user/video/...`) hoặc URL trang cá nhân (`https://www.tiktok.com/@creator`).
  * Tải luồng video MP4 trực tiếp không chứa watermark (No-Watermark) bằng thư viện `yt-dlp` hoặc API trung gian (TikWM API).
  * Trích xuất toàn bộ metadata: ID video, tiêu đề, danh sách hashtags, tác giả, thời lượng (duration).

### Module 2: Bộ Xử Lý Dữ Liệu & Hàng Đợi (`sync_manager.py`)
* **Chức năng**:
  * **Chống trùng lặp (Deduplication)**: Sử dụng SQLite (`sync_history.db`) lưu các ID TikTok đã đăng thành công để không bao giờ đăng lại video cũ.
  * **Chuẩn hóa nội dung**: Tự động ghép nối tiêu đề + hashtag, làm sạch các ký tự đặc biệt, kiểm soát độ dài theo chuẩn UCircle (<= 2200 ký tự).
  * **Quản lý file tạm**: Video chỉ tồn tại trong thư mục tạm trong lúc tải, kiểm tra và upload. Xóa file `.mp4` ngay khi endpoint upload của UCircle trả về HTTP `2xx`; quá trình encode/kiểm duyệt tiếp tục được theo dõi bằng `ucircle_video_id`, không cần giữ file nhị phân.
  * **Lưu metadata thống kê**: SQLite chỉ lưu TikTok ID, creator, source URL, UCircle video ID, duration, file size, hash, caption, timestamp, trạng thái, số lần retry, error code và latency. Không lưu bản sao video lâu dài.

### Module 3: UCircle Wavee API Client (`ucircle_client.py`)
* **Chức năng**:
  * **Auth Manager**: Đăng nhập tự động bằng Email/Password, tự động làm mới Access Token (Token Refresh) khi hết hạn.
  * **Quota Validator**: Gọi RPC `rpc_ucircle_wavee_caps_self` để kiểm tra số phút còn lại trong tài khoản và giới hạn thời lượng video (`max_seconds`).
  * **Intent Creator**: Gọi RPC `rpc_ucircle_wavee_upload_intent` gửi caption, visibility (`public`/`connections`), circle_id.
  * **Provision Fetcher**: Gửi POST request tới `https://ucircle.net/api/v1/ucircle/wavee/provision` để nhận Upload URL.
  * **Stream Uploader**: Gửi file nhị phân với thanh tiến trình (Progress Bar).
  * **Encoder Polling**: Lắng nghe trạng thái encode từ bảng `ucircle_wavee_video` cho đến khi video sẵn sàng xem được.

### Module 4: Giao diện Điều khiển & Lập lịch (`cli_runner.py` / `web_ui.py`)
* **Chế độ 1 - Đồng bộ Thủ công (CLI)**: Nhập link video bất kỳ và nhấn Enter để tải & đăng ngay lập tức.
* **Chế độ 2 - Tự động định kỳ (Daemon/Cron)**: Lên lịch mỗi 15 - 30 phút quét danh sách kênh TikTok đã lưu trong cấu hình, tự động đăng tải video mới nhất.
* **Chế độ 3 - Web UI / Dashboard (Tùy chọn)**: Giao diện trực quan xem lịch sử đăng, danh sách kênh theo dõi, trạng thái tài khoản UCircle.

---

## 4. KẾ HOẠCH TRIỂN KHAI THEO GIAI ĐOẠN (ROADMAP & PHASES)

| Giai đoạn | Nội dung công việc | Kết quả đầu ra (Deliverables) |
| :--- | :--- | :--- |
| **Giai đoạn 1**<br>*(Khởi tạo & Kết nối)* | 1. Trích xuất chính xác cấu hình `SUPABASE_URL` và `SUPABASE_ANON_KEY` từ UCircle.<br>2. Viết Module Auth & Client API kết nối thành công tới UCircle.<br>3. Kiểm tra gọi thử nghiệm RPC Quota & Intent. | File `ucircle_client.py` có thể đăng nhập và trả về User Profile + Hạn mức Wavee. |
| **Giai đoạn 2**<br>*(Tải TikTok & Pipeline Upload)* | 1. Viết Module tải video TikTok không watermark.<br>2. Viết hàm upload file MP4 lên Stream URL của UCircle.<br>3. Ghép nối luồng: Nhập 1 link TikTok -> Tải về -> Upload lên UCircle thành công. | Kịch bản CLI đồng bộ video đơn lẻ hoạt động 100%. |
| **Giai đoạn 3**<br>*(Metadata & Chống trùng lặp)* | 1. Tích hợp SQLite Database lưu lịch sử (`tiktok_id` ↔ `ucircle_video_id`) và số liệu thống kê.<br>2. Xóa tệp tạm ngay sau khi UCircle xác nhận upload HTTP `2xx`.<br>3. Nếu kết quả upload không rõ do timeout, kiểm tra remote trước khi xóa hoặc upload lại.<br>4. Nếu encode thất bại sau khi file đã xóa, tải lại từ nguồn và retry theo job cũ; chỉ tạo intent thay thế sau khi xác minh remote record cũ không thể tái sử dụng. | Hệ thống chỉ giữ metadata, không lưu video lâu dài, không đăng trùng và không làm đầy ổ đĩa. |
| **Giai đoạn 4**<br>*(Tự động hóa toàn diện & Daemon)* | 1. Xây dựng danh sách theo dõi nhiều kênh TikTok (`channels.json`).<br>2. Viết vòng lặp Daemon tự động quét video mới theo chu kỳ định sẵn.<br>3. Ghi log hoạt động (`sync.log`) và gửi thông báo qua Telegram/Discord (tùy chọn). | Tool chạy ngầm 24/7 hoàn toàn tự động trên máy/VPS. |

---

## 5. CẤU HÌNH BIẾN MÔI TRƯỜNG (`.env`)

File cấu hình mẫu cho hệ thống:

```ini
# ==========================================
# CẤU HÌNH TÀI KHOẢN UCIRCLE
# ==========================================
UCIRCLE_EMAIL=your_email@example.com
UCIRCLE_PASSWORD=your_secure_password
UCIRCLE_BASE_URL=https://ucircle.net

# ==========================================
# THÔNG SỐ SUPABASE CỦA UCIRCLE
# ==========================================
SUPABASE_URL=https://<your-supabase-id>.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOi...<anon_key>...

# ==========================================
# CẤU HÌNH ĐỒNG BỘ
# ==========================================
DEFAULT_VISIBILITY=public
DEFAULT_CIRCLE_ID=null
AUTO_SYNC_INTERVAL_MINUTES=30
MAX_VIDEO_DURATION_SECONDS=180
```

---

## 6. QUẢN TRỊ RỦI RO & LƯU Ý KỸ THUẬT

1. **Hạn mức tài khoản UCircle**:
   * Mỗi tài khoản có trần thời lượng (ví dụ: 60s, 180s) và tổng dung lượng lưu trữ (Quota Minutes). Cần kiểm tra trước khi upload để tránh bị server từ chối (`UCIRCLE_WAVEE_STORAGE_QUOTA_EXCEEDED`).
2. **Bản quyền & Giới hạn tải TikTok**:
   * TikTok có thể thay đổi thuật toán chặn tải hoặc rate-limit IP nếu gửi quá nhiều request liên tục. Cần thiết lập thời gian nghỉ (`delay: 5 - 10s`) giữa các lần tải.
3. **Bảo mật phiên đăng nhập**:
   * Quản lý Access Token an toàn, tự động refresh token để không bị gián đoạn khi chạy ngầm trong thời gian dài.
