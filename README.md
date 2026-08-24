# TOLLCAL - TikTok to UCircle Wavee Sync Tool

Hệ thống tự động hóa clone và đồng bộ video ngắn từ **TikTok** sang **Wavee (UCircle)** hoàn chỉnh, an toàn, có cơ chế chống đăng trùng (deduplication) và dọn dẹp file tạm tức thì.

---

## 🌟 1. Khởi chạy Giao diện Web (Khuyên Dùng - Dễ Nhất)

Bạn có thể mở giao diện đồ họa trực quan trên trình duyệt chỉ với 1 cú click:

- **Cách 1**: Nhấp đúp chuột vào file **`run_ui.bat`**
- **Cách 2**: Chạy lệnh trong terminal:
  ```bash
  python main.py ui
  ```

Trình duyệt sẽ tự động mở trang web **`http://127.0.0.1:8000`** với đầy đủ các tính năng:
- 🚀 **Dán link TikTok & Bấm Đồng Bộ** (Có thanh tiến trình thời gian thực 0% -> 100%).
- 🔐 **Đăng nhập Email OTP UCircle trực quan** (Xem chi tiết số phút lưu trữ còn lại).
- 📺 **Quản lý danh sách kênh Creator theo dõi tự động**.
- 📊 **Xem bảng lịch sử video đã đồng bộ**.

---

## 2. Cài đặt thư viện môi trường

Nếu là lần đầu tiên chạy trên máy mới:

```bash
pip install -r requirements.txt
```

---

## 3. Hoặc Sử Dụng Bằng Dòng Lệnh (CLI)

- **Đăng nhập OTP qua terminal**:
  ```bash
  python main.py login
  ```
- **Kiểm tra kết nối & hạn mức**:
  ```bash
  python main.py test-ucircle
  ```
- **Đồng bộ 1 video TikTok**:
  ```bash
  python main.py sync-url "https://vt.tiktok.com/ZSjxxxxxx/"
  ```
- **Quét toàn bộ video từ 1 kênh TikTok (Link Extractor)**:
  ```bash
  python main.py scan-channel "@username" --limit 100 --output "danh_sach.xlsx"
  ```
- **Chạy Daemon tự động quét nền 24/7**:
  ```bash
  python main.py daemon
  ```

---

## 🚀 4. Tính năng mới: Quét Toàn Bộ Video Kênh TikTok (Channel Scanner)

Hệ thống tích hợp công cụ quét toàn bộ video từ bất kỳ trang cá nhân / kênh TikTok nào (tương tự `TikTokLinkExtractor`):
- **Tốc độ siêu nhanh:** Chỉ ~2 - 4 giây để quét 100 video (lấy trọn vẹn Link, Tiêu đề, Hashtag, Thời lượng, Ảnh bìa, Lượt xem).
- **Thao tác 1 click trên Web UI:**
  1. Mở tab **"Quét Kênh TikTok"**.
  2. Dán link kênh (hoặc `@username`) và bấm **"Bắt Đầu Quét Video"**.
  3. Bấm **"Chuyển Sang Tải Hàng Loạt"** (để sync ngay sang UCircle) hoặc **"Xuất File Excel (.xlsx)"**.

