# NGHIÊN CỨU HƯỚNG TRIỂN KHAI CHI TIẾT

## Hệ thống đồng bộ video TikTok sang UCircle Wavee

**Ngày nghiên cứu:** 17/08/2026  
**Mục tiêu:** biến kế hoạch ban đầu thành một lộ trình có thể kiểm chứng, có điểm dừng Go/No-Go, kiến trúc rõ ràng và dự toán chi phí.

> Kết luận ngắn: dự án **khả thi về kỹ thuật cho một tài khoản UCircle và khối lượng nhỏ/trung bình**, vì frontend công khai của UCircle hiện đã có đầy đủ flow tạo video và upload. Tuy nhiên, đây chưa phải API công khai có hợp đồng ổn định. Rủi ro lớn nhất không nằm ở việc viết Python mà nằm ở: quyền sử dụng nội dung TikTok, độ ổn định của nguồn TikTok, thay đổi API nội bộ UCircle và trạng thái kiểm duyệt sau upload.

---

## 1. Những gì đã được xác minh

### 1.1. UCircle Wavee

Từ bundle frontend công khai hiện tại của UCircle, có thể xác nhận flow upload đang dùng:

1. Đăng nhập qua Supabase Auth và lấy access token.
2. Gọi RPC `rpc_ucircle_wavee_caps_self` để lấy:
   - gói/tier;
   - `max_seconds`;
   - giới hạn MB;
   - số phút lưu trữ đã dùng/còn lại.
3. Gọi RPC `rpc_ucircle_get_config` để đọc cấu hình mặc định, gồm visibility.
4. Gọi RPC `rpc_ucircle_wavee_upload_intent` với caption, circle ID và visibility.
5. Gọi `POST /api/v1/ucircle/wavee/provision` với Bearer token và `video_id`.
6. Nhận `upload_url`, sau đó gửi `multipart/form-data`, field tên `file`.
7. Poll bảng `ucircle_wavee_video`, hiện frontend poll khoảng 2,5 giây/lần và timeout khoảng 120 giây.
8. Upload có thể đạt trạng thái encoded nhưng vẫn phải qua moderation. Video chưa chắc xuất hiện công khai ngay.

Các mã lỗi/điều kiện cũng được xác nhận trong frontend, gồm quota lưu trữ, video quá lớn, không phải video, lỗi encode, mất mạng và session hết hạn.

**Đánh giá khả thi:** cao cho PoC, trung bình-cao cho tool nội bộ, trung bình-thấp nếu muốn bán như SaaS mà chưa có thỏa thuận API với UCircle.

**Điểm cần sửa trong kế hoạch cũ:** `HEAD` tới endpoint provision trả 404 không có nghĩa endpoint không tồn tại; frontend gọi nó bằng `POST`. Ngoài ra, “upload thành công” và “publish công khai” phải là hai trạng thái khác nhau.

### 1.2. TikTok

- `yt-dlp` hiện vẫn liệt kê TikTok video và `tiktok:user` là nguồn được hỗ trợ; một số extractor khác như tag/sound đang có thể hỏng. Điều này cho thấy downloader cần được coi là adapter có thể thay thế, không phải nền tảng ổn định tuyệt đối.
- TikTok Display API chính thức cho phép đọc profile và danh sách video công khai của **người dùng đã cấp quyền**, qua `user.info.basic` và `video.list`. Nó không phải API để tùy ý theo dõi và tải MP4 của mọi creator.
- TikTok Research API không phù hợp cho sản phẩm này vì giới hạn đối tượng nghiên cứu và cần xét duyệt.
- Điều khoản TikTok hiện cấm dùng script tự động để thu thập/tương tác và hạn chế download/sao chép nội dung nếu không có quyền. Vì vậy hướng sản phẩm an toàn nhất là chỉ đồng bộ:
  - video do chính người vận hành sở hữu;
  - video của creator đã ủy quyền;
  - nội dung có giấy phép rõ ràng.

**Đánh giá khả thi:**

- URL video đơn lẻ bằng `yt-dlp`: cao nhưng dễ bị thay đổi theo thời gian.
- Tự động theo dõi kênh đã được creator cấp quyền: trung bình-cao.
- Tự động clone mọi kênh công khai: kỹ thuật trung bình, pháp lý/ToS thấp và không nên chọn làm thiết kế mặc định.

---

## 2. Quyết định kiến trúc đề xuất

### 2.1. Stack

- **Python 3.11/3.12**: phù hợp nhất với `yt-dlp`, CLI, SQLite và daemon.
- **Typer**: CLI.
- **Pydantic Settings**: cấu hình và validation `.env`.
- **Supabase Python SDK** hoặc REST trực tiếp: Auth và RPC.
- **httpx**: provision, polling và các HTTP call còn lại.
- **yt-dlp + FFmpeg/ffprobe**: download, đọc metadata, kiểm tra codec/thời lượng và tùy chọn cắt/chuyển mã.
- **SQLite + Alembic**: MVP và một worker. Chuyển PostgreSQL khi có nhiều worker/máy.
- **APScheduler** hoặc vòng scheduler riêng: bản đầu. Không cần Celery/Redis ở quy mô một host.
- **FastAPI**: chỉ thêm khi làm dashboard/API; không cần cho MVP CLI.
- **Docker Compose** hoặc native systemd/Windows Service: deployment.

### 2.2. Nguyên tắc thiết kế

1. **Adapter hóa hai đầu:** TikTok và UCircle đều có khả năng thay đổi.
2. **Idempotent, không hứa exactly-once:** mạng có thể mất sau khi server đã nhận request. Dùng khóa duy nhất và lưu remote ID để phục hồi.
3. **State machine rõ ràng:** không dùng một cột `success=true/false` cho toàn bộ pipeline.
4. **File tạm có vòng đời ngắn:** xóa ngay khi endpoint upload UCircle trả HTTP `2xx`. Encode và moderation tiếp tục được theo dõi bằng `ucircle_video_id`, không cần giữ binary video.
5. **Không phụ thuộc dashboard:** core pipeline phải chạy và test được hoàn toàn bằng CLI.
6. **Secrets không vào database/log/git.** Supabase anon key có thể xuất hiện trong frontend, nhưng email/password, access token và refresh token vẫn là bí mật.
7. **Quyền nội dung là dữ liệu bắt buộc:** mỗi source/channel có `rights_basis` và trạng thái được phép đồng bộ.
8. **Không dùng object storage cho video ở MVP:** local disk chỉ là cache cho 1-2 job đang chạy. Hệ thống giữ metadata thống kê, không giữ bản sao video.

### 2.3. Sơ đồ thành phần

```text
CLI / Scheduler / Optional Web API
              |
              v
        Sync Orchestrator
       /        |        \
      v         v         v
Source Adapter  Media     UCircle Adapter
(TikTok/local)  Validator (Auth/RPC/Upload/Poll)
      \         |         /
       \        v        /
        Job State Machine
               |
               v
       SQLite + structured logs
```

### 2.4. Cấu trúc source code

```text
tollcal/
  pyproject.toml
  .env.example
  src/tollcal/
    config.py
    cli.py
    domain/
      models.py
      states.py
      errors.py
    sources/
      base.py
      tiktok_ytdlp.py
      tiktok_authorized.py
      local_file.py
    media/
      probe.py
      normalize.py
      temp_files.py
    ucircle/
      auth.py
      client.py
      models.py
    sync/
      orchestrator.py
      retry.py
      dedup.py
    storage/
      database.py
      repositories.py
      migrations/
    scheduler/
      service.py
    observability/
      logging.py
      metrics.py
  tests/
    unit/
    integration/
    fixtures/
  data/
  temp/
```

---

## 3. Flow dữ liệu chuẩn

### 3.1. Đồng bộ một URL

1. Người dùng nhập URL và xác nhận quyền sử dụng nội dung.
2. Normalize URL, theo redirect an toàn và lấy TikTok video ID.
3. Tạo/cập nhật job với unique key `(source_type, source_video_id, target_account_id)`.
4. Nếu đã `PUBLISHED`, `UNDER_REVIEW` hoặc `ENCODED`, dừng với trạng thái duplicate.
5. Extract metadata trước; chưa tải file ngay nếu job đã trùng.
6. Tải vào file `.part`, sau đó rename nguyên tử thành `.mp4` khi hoàn tất.
7. Dùng ffprobe kiểm tra:
   - file thực sự là video;
   - duration;
   - kích thước;
   - stream video/audio;
   - container/codec có khả năng tương thích.
8. Gọi UCircle caps. Nếu quá thời lượng/dung lượng/quota, chuyển `BLOCKED_POLICY`, không retry mù quáng.
9. Tạo upload intent và lưu `ucircle_video_id` **trước** khi provision/upload.
10. Provision signed URL.
11. Multipart upload field `file`, có timeout và progress.
12. Nếu endpoint upload trả HTTP `2xx`:
    - ghi `uploaded_at`, kích thước, hash và upload latency;
    - chuyển job sang `PROCESSING`;
    - xóa file video cục bộ ngay lập tức.
13. Nếu request timeout hoặc mất mạng mà không có kết quả chắc chắn, chưa xóa file; query remote bằng `ucircle_video_id` trước khi quyết định retry.
14. Poll đến encoded/failed/timeout.
15. Nếu encoded:
    - lưu `ENCODED`;
    - đọc moderation state;
    - nếu chưa public, chuyển `UNDER_REVIEW`;
16. Nếu encode thất bại sau khi file đã xóa, job retry sẽ tải lại từ nguồn. Ưu tiên tái sử dụng remote record cũ nếu UCircle cho phép; chỉ tạo intent thay thế sau khi xác minh record cũ không thể tiếp tục.
17. Một reconciler chạy sau đó tiếp tục poll các job `UNDER_REVIEW` để ghi nhận `PUBLISHED`, `BLOCKED` hoặc trạng thái mới.

### 3.2. State machine

```text
DISCOVERED
  -> METADATA_READY
  -> DOWNLOADING
  -> VALIDATED
  -> INTENT_CREATED
  -> PROVISIONED
  -> UPLOADING
  -> PROCESSING
  -> ENCODED
  -> UNDER_REVIEW
  -> PUBLISHED

Nhánh kết thúc khác:
DUPLICATE | BLOCKED_POLICY | BLOCKED_MODERATION | FAILED_PERMANENT

Nhánh phục hồi:
RETRY_WAIT -> quay lại bước an toàn gần nhất
```

Không tạo intent mới nếu job đã có `ucircle_video_id`, trừ khi đã xác minh remote record không còn tồn tại. Đây là điểm chống đăng trùng quan trọng nhất.

Binary video chỉ tồn tại đến khi kết thúc `UPLOADING`. Từ `PROCESSING` trở đi, hệ thống chỉ làm việc với metadata và remote ID.

### 3.3. Theo dõi nhiều kênh

1. Scheduler chọn channel đến hạn theo `next_scan_at`.
2. Source adapter đọc danh sách video mới với cursor/checkpoint.
3. Chỉ enqueue ID chưa từng thấy; không tải toàn bộ ngay.
4. Sắp theo thời gian tăng dần để giữ đúng thứ tự đăng.
5. Áp giới hạn mỗi channel và tổng toàn hệ thống.
6. Thêm jitter 10-20% để không request đồng loạt.
7. Nếu extractor bị rate-limit, tăng backoff ở cấp channel, không làm chậm các channel khác.

---

## 4. Kế hoạch triển khai từng bước

Các ước lượng dưới đây là **person-day (PD), 1 PD = 8 giờ**, dành cho một developer đã quen Python/HTTP. Chi phí dịch vụ trực tiếp chưa bao gồm công phát triển.

### Bước 0 — Chốt phạm vi và quyền sử dụng

**Mục tiêu:** tránh xây đúng kỹ thuật nhưng sai mô hình vận hành.

**Việc làm:**

- Chỉ rõ tool dùng nội bộ hay bán cho nhiều khách hàng.
- Chỉ rõ video là của chính bạn, creator ủy quyền hay nguồn khác.
- Yêu cầu mỗi channel có `rights_basis`: `owner`, `licensed`, `creator_oauth`, `manual_approval`.
- Xin xác nhận từ UCircle rằng tài khoản được phép dùng flow tự động, đặc biệt nếu chạy số lượng lớn.
- Xác định SLA: tối đa bao nhiêu phút từ TikTok đến Wavee, số video/ngày, số channel.

**Khả thi:** cao nếu nội dung thuộc quyền sở hữu; thấp nếu mục tiêu là clone tùy ý nội dung của người khác.

**Điều kiện hoàn tất:** có văn bản phạm vi một trang và danh sách nguồn hợp lệ.

**Thời gian:** 0,5-1 PD.  
**Chi phí trực tiếp:** 0; có thể phát sinh tư vấn pháp lý riêng nếu thương mại hóa.

### Bước 1 — PoC UCircle trước mọi thứ khác

**Mục tiêu:** chứng minh đường đích hoạt động bằng một video test tự tạo, không liên quan TikTok.

**Việc làm:**

- Tạo tài khoản test UCircle riêng.
- Đăng nhập Supabase bằng email/password.
- Test refresh session.
- Gọi caps và ghi lại response schema thực tế.
- Tạo video màu 5-10 giây bằng FFmpeg.
- Tạo intent, provision, upload multipart và poll.
- Ghi lại cả trạng thái encode và moderation/publish.
- Lặp lại ít nhất ba lần ở các thời điểm khác nhau.
- Lưu sanitized HTTP fixture để làm contract test, không lưu token.

**Kiến trúc:** chỉ xây `ucircle/client.py` và một script `poc_ucircle.py`; chưa xây database/dashboard.

**Khả thi:** cao dựa trên frontend hiện tại, nhưng cần credential thật và quota đủ.

**Go/No-Go:**

- **Go** nếu 3/3 video tạo intent, upload và encode; refresh token hoạt động.
- **Tạm dừng** nếu upload được nhưng không có cơ chế theo dõi moderation.
- **No-Go** nếu UCircle chặn automation hoặc API thay đổi/không cho phép dùng ngoài frontend.

**Thời gian:** 2-4 PD.  
**Chi phí trực tiếp:** gần 0 ngoài gói/quota UCircle; chi phí UCircle chưa có bảng giá công khai để dự toán chắc chắn.

### Bước 2 — Khởi tạo repository và nền tảng chất lượng

**Mục tiêu:** tạo khung đủ nhỏ nhưng không phải viết lại sau PoC.

**Việc làm:**

- `pyproject.toml`, dependency lock, lint, type check, pytest.
- `.env.example`, `.gitignore`, thư mục temp/data.
- Structured logging JSON và correlation ID/job ID.
- Error taxonomy: retryable, permanent, policy, auth, quota.
- Test unit cho config và state transition.

**Khả thi:** rất cao.

**Điều kiện hoàn tất:** chạy được `lint + test`, không có secret trong repo.

**Thời gian:** 1 PD.  
**Chi phí trực tiếp:** 0.

### Bước 3 — Hoàn thiện UCircle Adapter

**Mục tiêu:** đóng gói API UCircle sau một interface ổn định của chính dự án.

**Interface đề xuất:**

```python
class UCircleGateway:
    async def get_caps(self) -> WaveeCaps: ...
    async def create_intent(self, request: UploadIntentRequest) -> UploadIntent: ...
    async def provision(self, video_id: str) -> Provision: ...
    async def upload(self, provision: Provision, file_path: Path) -> None: ...
    async def get_video(self, video_id: str) -> RemoteVideo: ...
```

**Việc làm:**

- Token lifecycle có lock để nhiều job không refresh đồng thời.
- Timeout riêng cho auth/RPC/provision/upload/poll.
- Không log authorization header, password, refresh token hoặc signed URL đầy đủ.
- Mapping error UCircle sang error nội bộ.
- Contract test dùng tài khoản test và video nhỏ.
- Canary test hằng ngày chỉ gọi caps; không tự tạo video để tránh tốn quota.

**Khả thi:** cao cho một tài khoản; cần thiết kế lại credential store nếu multi-tenant.

**Điều kiện hoàn tất:** adapter vượt contract test và PoC không còn chứa logic HTTP rời rạc.

**Thời gian:** 3-5 PD.  
**Chi phí trực tiếp:** 0-chi phí quota UCircle test.

### Bước 4 — Source Adapter TikTok

**Mục tiêu:** lấy metadata và file từ một URL qua interface có thể thay thế.

**Việc làm:**

- `SourceProvider` trả về `SourceVideo` chuẩn hóa.
- Bản đầu dùng `yt-dlp`, pin phiên bản; có lệnh nâng cấp riêng.
- Chạy extractor trong subprocess có timeout để sự cố extractor không treo daemon.
- Lấy video ID, creator, title, hashtags, upload timestamp, duration, source URL.
- Test URL dài, `vm.tiktok.com`, `vt.tiktok.com`, URL canonical.
- Không mặc định dùng TikWM/API không có SLA và privacy contract.
- Thêm `LocalFileSource` để test pipeline không phụ thuộc TikTok.

**Kiến trúc:** UCircle không được biết `yt-dlp`; orchestrator chỉ nhận model chuẩn.

**Khả thi:** cao cho video đơn; trung bình cho channel scan lâu dài.

**Go/No-Go:** ba loại URL thực tế tải thành công, ID/metadata đúng, lỗi private/deleted/rate-limit được phân loại.

**Thời gian:** 2-4 PD.  
**Chi phí trực tiếp:** 0; chưa dùng proxy và chưa dùng paid scraper.

### Bước 5 — Media validation và normalization

**Mục tiêu:** từ chối sớm file không thể đăng, tránh tiêu tốn intent/quota.

**Việc làm:**

- ffprobe duration, size, streams, codec, dimensions và aspect ratio.
- So sánh với caps UCircle động, không hard-code 180 giây.
- Caption builder giới hạn độ dài, giữ Unicode và hashtag hợp lệ.
- Chính sách mặc định: không transcode nếu file hợp lệ.
- Chỉ dùng FFmpeg khi cần cắt/chuyển container; đặt giới hạn CPU và timeout.
- Tạo hash file để audit và phát hiện file bị thay đổi.

**Khả thi:** rất cao.

**Điều kiện hoàn tất:** bộ fixture gồm video hợp lệ, quá dài, không audio, file giả MP4, file hỏng.

**Thời gian:** 1-2 PD.  
**Chi phí trực tiếp:** 0; FFmpeg là mã nguồn mở. Transcode làm tăng yêu cầu CPU nếu dùng thường xuyên.

### Bước 6 — Vertical slice: một URL đến UCircle

**Mục tiêu:** CLI thực hiện được toàn flow thật.

**Lệnh dự kiến:**

```text
tollcal sync-url <tiktok-url> --visibility public --rights owner
```

**Việc làm:**

- Nối source → validate → caps → intent → provision → upload → poll.
- In progress và kết quả cuối rõ ràng.
- Ctrl+C hủy download/upload an toàn.
- File tạm xóa ngay sau khi endpoint upload trả HTTP `2xx`.
- Nếu upload thất bại rõ ràng, file có thể giữ tối đa 1 giờ để retry; nếu kết quả không rõ do timeout, kiểm tra remote trước khi xóa hoặc gửi lại.
- Nếu encode thất bại sau khi file đã xóa, tải lại từ nguồn thay vì duy trì kho video.
- Không coi `UNDER_REVIEW` là `PUBLISHED`.

**Khả thi:** cao sau khi Bước 1 và 4 đạt gate.

**Điều kiện hoàn tất:** 10 video test liên tiếp không crash, trạng thái remote đúng và không rò file tạm.

**Thời gian:** 2-3 PD.  
**Chi phí trực tiếp:** băng thông nhỏ, thường nằm trong mạng/VPS sẵn có; quota UCircle là biến số.

### Bước 7 — SQLite, deduplication và phục hồi

**Mục tiêu:** không đăng trùng khi process bị restart hoặc mạng mất giữa chừng.

**Bảng tối thiểu:**

```text
source_channels
source_videos
sync_jobs
sync_attempts
remote_videos
app_settings
```

**Ràng buộc quan trọng:**

- unique `(source_provider, source_video_id, target_account_id)`;
- unique `ucircle_video_id` khi khác null;
- lưu `state`, `last_safe_state`, `attempt_count`, `next_retry_at`, `error_code`;
- transaction khi reserve job;
- heartbeat/lease để phát hiện worker chết.

**Metadata thống kê cần giữ:**

- TikTok video ID, creator ID và source URL;
- UCircle video ID;
- duration, file size và SHA-256;
- caption/visibility/circle ID;
- downloaded/uploaded/encoded/published timestamp;
- moderation state, attempt count và error code;
- thời gian download, upload, encode và tổng latency.

**Flow phục hồi:**

- Có remote ID: query remote trước, không tạo intent mới.
- Đang download: xóa `.part` quá TTL rồi tải lại.
- Upload không rõ kết quả: giữ file tạm ngắn hạn và query remote; chỉ upload lại nếu remote chưa nhận/encode và URL còn hạn.
- Upload đã trả `2xx`: file cục bộ đã bị xóa; nếu encode thất bại, tải lại nguồn khi retry.
- Encoded: không upload lại dù moderation chưa xong.

**Khả thi:** rất cao cho một worker; SQLite WAL đủ cho MVP.

**Điều kiện hoàn tất:** kill process ở từng state, restart và không tạo duplicate.

**Thời gian:** 2-4 PD.  
**Chi phí trực tiếp:** 0.

### Bước 8 — Retry, quota và failure policy

**Mục tiêu:** daemon tự phục hồi nhưng không spam endpoint.

**Retry được:** timeout, 429, 5xx, signed URL hết hạn, lỗi mạng tạm thời.

**Không retry tự động:** sai credential, không có quyền, video private/deleted, quá duration, hết storage quota, file không phải video, moderation block.

**Backoff đề xuất:** 30 giây, 2 phút, 10 phút, 30 phút, 2 giờ; có jitter; tối đa theo từng error class.

**Việc làm:**

- Circuit breaker ngắn khi UCircle/TikTok lỗi hàng loạt.
- Quota check trước download hàng loạt và trước intent.
- Reconciler cho processing/under-review.
- Retry encode thất bại bằng cách tải lại nguồn; không phụ thuộc file đã upload trước đó.
- Dead-letter state cho job cần người xử lý.
- Lệnh `retry-job`, `inspect-job`, `cancel-job`.

**Khả thi:** cao.

**Điều kiện hoàn tất:** fault-injection cho timeout, 500, 429, disk full và token expired.

**Thời gian:** 3-5 PD.  
**Chi phí trực tiếp:** 0.

### Bước 9 — Channel monitor và scheduler

**Mục tiêu:** quét định kỳ các creator đã được phép.

**Việc làm:**

- Channel config trong database, không dùng `channels.json` làm nguồn sự thật lâu dài.
- Các mode:
  - `authorized_api`: creator OAuth/Display API cho discovery;
  - `ytdlp_user`: phương án kỹ thuật dễ vỡ hơn;
  - `manual_urls`: vận hành an toàn nhất lúc đầu.
- Cursor/checkpoint và giới hạn backfill.
- Mặc định lần đầu chỉ lấy 1-3 video mới nhất, không clone toàn bộ lịch sử.
- Scheduler 15-30 phút, jitter, per-channel backoff.
- Queue concurrency mặc định 1-2; không cần upload song song cao.

**Khả thi:** trung bình-cao cho ít channel; giảm dần khi số channel lớn hoặc nguồn không được cấp quyền.

**Go/No-Go:** chạy 7 ngày, không trùng, không bỏ sót video test và không bị rate-limit kéo dài.

**Thời gian:** 3-5 PD.  
**Chi phí trực tiếp:** bắt đầu cần máy chạy 24/7; VPS khuyến nghị khoảng 12 USD/tháng cho 1 vCPU/2 GB/50 GB ở bảng giá DigitalOcean hiện tại.

### Bước 10 — Deployment và bảo mật

**Mục tiêu:** chạy lại được sau reboot, có backup và không lộ credential.

**Việc làm:**

- Docker image pin version của Python, yt-dlp và FFmpeg; hoặc native service nếu Windows.
- Linux: systemd với restart policy, user không phải root, thư mục riêng.
- `.env` permission tối thiểu; tốt hơn dùng OS credential store/secret manager.
- Firewall: không cần mở inbound port nếu chỉ có CLI/daemon.
- Backup database mỗi ngày, giữ 7-30 bản; không backup video tạm mặc định.
- Log rotation, giới hạn temp disk và cleanup job.
- Health check gồm database writable, disk free, auth/caps canary.

**Khả thi:** rất cao.

**Điều kiện hoàn tất:** reboot host, service tự lên; restore database thành công trên host khác.

**Thời gian:** 2-3 PD.  
**Chi phí trực tiếp:** khoảng 0-12 USD/tháng tùy chạy máy cá nhân hay VPS; domain không cần thiết nếu không có dashboard.

### Bước 11 — Quan sát và cảnh báo

**Mục tiêu:** biết lỗi trước khi người dùng phát hiện.

**Metric tối thiểu:**

- discovered/downloaded/uploaded/encoded/published/blocked;
- latency từng stage;
- retry count theo error code;
- disk free;
- channel scan age;
- quota remaining;
- under-review age.

**Cảnh báo:** auth chết, canary caps thất bại, disk dưới 20%, job retry quá ngưỡng, không scan channel quá 2 chu kỳ, quota gần hết.

**Khả thi:** rất cao.

**Điều kiện hoàn tất:** Telegram/Discord nhận được alert test và alert không chứa secret/signed URL.

**Thời gian:** 1-2 PD.  
**Chi phí trực tiếp:** có thể bằng 0 với log + Telegram + Uptime Kuma; dịch vụ SaaS monitoring trả phí là tùy chọn.

### Bước 12 — Dashboard, chỉ làm sau khi daemon ổn định

**Mục tiêu:** vận hành thuận tiện, không thay đổi core pipeline.

**Màn hình:**

- tổng quan trạng thái và quota;
- channel list và quyền nội dung;
- job list/filter/error;
- retry/cancel thủ công;
- lịch sử remote video và moderation state;
- cấu hình caption/visibility/circle.

**Kiến trúc:** FastAPI gọi service layer hiện có; frontend mỏng. Không cho browser giữ UCircle password.

**Khả thi:** cao, nhưng không tăng độ khả thi của pipeline nên xếp sau.

**Điều kiện hoàn tất:** phân quyền, CSRF/auth, audit action và không thể tạo duplicate do double click.

**Thời gian:** 5-10 PD.  
**Chi phí trực tiếp:** có thể dùng chung VPS; domain/TLS khoảng 12-25 USD/năm tùy nhà cung cấp.

### Bước 13 — Pilot và quyết định scale

**Mục tiêu:** chứng minh độ ổn định trước khi tăng channel/video.

**Pilot đề xuất:**

- Tuần 1: 1 channel, 1-3 video/ngày.
- Tuần 2: 3 channel, tối đa 10 video/ngày.
- Tuần 3-4: 5-10 channel, theo quota thật.
- Theo dõi tỷ lệ download, encode, publish, thời gian moderation và số lần sửa adapter.

**Ngưỡng đạt:**

- không duplicate;
- ≥95% job hợp lệ encode không cần can thiệp;
- lỗi được phát hiện trong 15 phút;
- không có temp file quá TTL;
- API UCircle không thay đổi phá vỡ trong pilot;
- có quy trình xử lý nội dung bị block.

**Khả thi:** phụ thuộc thực tế UCircle/TikTok, đây là bước biến giả định thành số liệu.

**Thời gian kỹ thuật:** 3-5 PD phân tán trong 2-4 tuần.  
**Chi phí trực tiếp:** VPS + quota UCircle + thời gian vận hành.

---

## 5. Các cổng Go/No-Go

| Gate | Phải chứng minh | Nếu thất bại |
|---|---|---|
| A | Auth, refresh token và caps hoạt động | Không viết downloader/dashboard |
| B | 3 video test upload + encode thành công | Dừng, làm rõ với UCircle |
| C | 3 dạng URL TikTok tải và validate đúng | Giới hạn sản phẩm ở local/manual source |
| D | Kill/restart ở mọi state không gây duplicate | Chưa được chạy daemon |
| E | Pilot 7 ngày ổn định | Không tăng channel |
| F | Có quyền nội dung và chấp thuận vận hành | Không thương mại hóa |

Thứ tự này giúp cắt lỗ sớm. Không nên xây UI trước Gate D.

---

## 6. Dự toán chi phí

### 6.1. Công phát triển

| Mốc | Phạm vi | Tổng công ước lượng |
|---|---|---:|
| PoC | Gate A-B, chỉ UCircle | 2-4 PD |
| MVP thủ công | Bước 0-8, một URL, DB và retry | 17-29 PD |
| Daemon production nhỏ | Bước 0-11 và pilot | 26-44 PD |
| Có dashboard | Thêm Bước 12 | 31-54 PD |

Để chuyển thành tiền, dùng công thức:

```text
Chi phí phát triển = person-day x đơn giá/ngày
```

Tham khảo lập ngân sách, không phải báo giá thị trường cố định:

- Tự phát triển: tiền mặt thấp, đổi lại 26-44 ngày làm việc cho bản daemon ổn định.
- Freelancer tầm trung: khoảng 3-6 triệu VND/PD.
- Đội/agency có QA và quản lý: khoảng 6-12 triệu VND/PD.

Suy ra bản daemon production nhỏ có thể nằm khoảng:

- freelancer: **78-264 triệu VND**;
- agency: **156-528 triệu VND**.

Biên rất rộng vì chi phí lớn nhất là số vòng reverse-engineering, test với tài khoản thật và thay đổi API trong lúc làm. Nên ký theo milestone Gate A-B-C-D thay vì trả trọn gói từ đầu.

### 6.2. Chi phí vận hành hàng tháng

Quy đổi kế hoạch dùng **1 USD ≈ 26.000 VND**, chỉ để dự toán.

| Hạng mục | MVP nhỏ | Ghi chú |
|---|---:|---|
| Chạy trên máy cá nhân | 0-200.000 VND/tháng tăng thêm | Phụ thuộc điện, máy phải bật 24/7 |
| VPS khuyến nghị | ~12 USD ≈ 312.000 VND/tháng | DigitalOcean Basic 1 vCPU, 2 GiB, 50 GiB, 2 TB transfer tại thời điểm nghiên cứu |
| Backup DB/log | 0-2 USD/tháng | Chỉ backup SQLite và log cần thiết; không backup video tạm |
| Domain dashboard | ~12-25 USD/năm | Không cần nếu chỉ CLI/daemon |
| Telegram/Discord alert | 0 | Bot/webhook |
| Proxy/scraping API | 0 ở MVP | Chỉ cân nhắc sau khi có lỗi thực tế; có thể 10-100+ USD/tháng và không giải quyết rủi ro ToS |
| UCircle plan/quota | **chưa xác định** | Biến số quan trọng nhất, phải đọc từ caps và hỏi UCircle |

### 6.3. Ước lượng băng thông và disk

Ví dụ 100 video/ngày, trung bình 30 MB/video:

```text
Download TikTok: 100 x 30 MB x 30 ngày = 90 GB/tháng
Upload UCircle:  100 x 30 MB x 30 ngày = 90 GB/tháng
```

Phần upload sang UCircle là outbound của VPS, khoảng 90 GB/tháng, vẫn thấp hơn 2 TB đi kèm VPS ví dụ. Vì file bị xóa ngay sau HTTP `2xx`, disk chỉ chứa 1-2 job đang chạy. Với file tối đa khoảng 100-500 MB, giới hạn temp `2-5 GB` là đủ cho MVP. VPS 50 GB vẫn hữu ích cho hệ điều hành, log và khoảng trống an toàn, nhưng không được dùng làm kho video.

Nếu thường xuyên transcode, 1 vCPU sẽ chậm. Khi đó nâng lên 2 vCPU hoặc xử lý tuần tự ngoài giờ; chi phí có thể tăng gấp 1,5-3 lần. Thiết kế mặc định nên **pass-through, không transcode**.

### 6.4. Chi phí ẩn

- Thời gian bảo trì khi TikTok thay đổi extractor.
- Thời gian cập nhật contract khi UCircle đổi bundle/API/schema.
- Quota video UCircle và thời gian moderation.
- Xử lý khi creator xóa video hoặc thu hồi quyền.
- Khiếu nại bản quyền/kiểm duyệt nếu nguồn không được cấp phép.
- Vận hành thủ công cho dead-letter jobs.

Nên dự phòng bảo trì **1-3 PD/tháng** khi hệ thống còn phụ thuộc endpoint không công khai.

---

## 7. Ma trận rủi ro

| Rủi ro | Xác suất | Tác động | Cách giảm thiểu |
|---|---|---|---|
| UCircle đổi RPC/endpoint/schema | Trung bình-cao | Rất cao | Adapter riêng, contract canary, fixture, thỏa thuận API |
| TikTok extractor hỏng/rate-limit | Cao theo thời gian | Cao | Provider interface, pin/update yt-dlp, backoff, manual source fallback |
| Vi phạm quyền nội dung/ToS | Trung bình nếu scope lỏng | Rất cao | Chỉ owner/licensed/authorized, audit rights basis |
| Upload xong nhưng chưa publish | Cao | Trung bình | State `UNDER_REVIEW`, reconciler, không báo sai “đã đăng” |
| Duplicate khi timeout/restart | Trung bình | Cao | Unique key, lưu remote ID sớm, query trước retry |
| Hết quota UCircle | Trung bình | Cao | Caps check, alert ngưỡng, rate limit intake |
| Lộ credential/token/signed URL | Thấp-trung bình | Rất cao | Secret store, log redaction, least privilege, rotate |
| Disk đầy do file lỗi | Trung bình | Cao | TTL, disk quota, cleanup, alert 20% |
| Codec/file không tương thích | Trung bình | Trung bình | ffprobe, fixture, transcode fallback có kiểm soát |
| SQLite lock/corrupt khi scale | Thấp ở một worker | Trung bình | WAL, transaction ngắn; chuyển PostgreSQL khi nhiều worker |

---

## 8. Khi nào cần nâng kiến trúc

Giữ SQLite + một daemon cho đến khi xuất hiện một trong các điều kiện:

- hơn 2 worker ghi database đồng thời;
- hơn 100-300 job đang hoạt động;
- nhiều tài khoản UCircle/tenant;
- cần HA hoặc chạy trên nhiều máy;
- dashboard có nhiều người dùng và phân quyền.

Khi đó chuyển sang:

- PostgreSQL;
- queue bền vững như Redis Streams/RQ, Celery hoặc RabbitMQ;
- object storage có TTL chỉ khi nhiều worker cần handoff qua nhiều máy; không dùng làm kho video mặc định;
- worker riêng cho download, upload và reconciliation;
- secret manager theo tenant.

Không nên đưa các thành phần này vào MVP vì làm tăng chi phí và số failure mode mà chưa giải quyết rủi ro chính.

---

## 9. Backlog ưu tiên thực tế

### Sprint 1 — Feasibility

- Bước 0.
- PoC auth/caps.
- PoC intent/provision/upload/poll bằng video test.
- Báo cáo Gate A-B.

### Sprint 2 — Single-video MVP

- Repository skeleton.
- UCircle adapter.
- TikTok/local source adapter.
- ffprobe/caption policy.
- CLI vertical slice.

### Sprint 3 — Reliability

- SQLite/schema.
- Idempotency/recovery.
- Retry/circuit breaker.
- Temp cleanup và fault tests.

### Sprint 4 — Automation

- Channel scheduler.
- Reconciler moderation/publish.
- Deployment/service.
- Monitoring/alerts.

### Sprint 5 — Pilot, rồi mới quyết định UI

- Pilot tăng dần.
- Đo tỷ lệ thành công và chi phí thật.
- Chỉ xây dashboard nếu thao tác CLI trở thành chi phí vận hành đáng kể.

---

## 10. Khuyến nghị cuối cùng

1. **Bắt đầu bằng Bước 1, không bắt đầu bằng downloader hoặc Web UI.** UCircle là dependency quyết định sống còn.
2. **MVP chỉ hỗ trợ URL đơn và nội dung có quyền sử dụng.** Channel monitoring thêm sau khi dedup/recovery đã được chứng minh.
3. **Coi UCircle là private/internal API.** Tool nội bộ có thể chấp nhận; sản phẩm thương mại cần hợp đồng hoặc API chính thức.
4. **Không dùng TikWM làm đường chính.** `yt-dlp` + provider abstraction minh bạch và dễ thay thế hơn; LocalFileSource là fallback bắt buộc.
5. **Xóa binary ngay sau upload `2xx`; chỉ giữ metadata.** Nếu encode lỗi thì tải lại nguồn, chấp nhận thêm băng thông để đổi lấy hệ thống không cần kho video.
6. **Tách encoded, under review và published.** Đây là khác biệt quan trọng giữa pipeline demo và hệ thống vận hành đúng.
7. **Dự toán bản daemon đáng tin cậy là 26-44 PD**, không phải vài file script, vì phần khó là recovery, idempotency và thay đổi bên thứ ba.
8. **Chi phí server nhỏ; chi phí con người và rủi ro API mới là chính.** VPS khoảng vài trăm nghìn VND/tháng, nhưng bảo trì có thể tốn 1-3 ngày công/tháng.

---

## 11. Nguồn tham khảo

Các nguồn được đọc ngày 17/08/2026:

- UCircle public app: <https://ucircle.net/app>
- UCircle current Wavee upload bundle: <https://ucircle.net/assets/WaveeUploadPage-BOnkRnLA.js>
- UCircle current main bundle: <https://ucircle.net/assets/app-BbW0pvlu.js>
- Supabase password auth: <https://supabase.com/docs/reference/javascript/auth-signinwithpassword>
- Supabase refresh session: <https://supabase.com/docs/reference/javascript/auth-refreshsession>
- yt-dlp supported sites: <https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md>
- yt-dlp releases: <https://github.com/yt-dlp/yt-dlp/releases>
- TikTok Display API overview: <https://developers.tiktok.com/doc/display-api-overview/>
- TikTok Research API: <https://developers.tiktok.com/products/research-api/>
- TikTok Terms of Service: <https://www.tiktok.com/legal/page/row/terms-of-service/en>
- DigitalOcean Droplet pricing: <https://www.digitalocean.com/pricing/droplets>

Bundle UCircle có tên chứa hash và có thể đổi sau mỗi lần deploy. Vì vậy link bundle là bằng chứng tại thời điểm nghiên cứu, không phải API contract lâu dài.
