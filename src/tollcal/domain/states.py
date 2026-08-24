from enum import Enum


class JobState(str, Enum):
    """Trạng thái vòng đời của một tiến trình đồng bộ video."""

    DISCOVERED = "DISCOVERED"              # Phát hiện URL / video mới
    METADATA_READY = "METADATA_READY"      # Đã lấy xong metadata cơ bản
    DOWNLOADING = "DOWNLOADING"            # Đang tải file video tạm
    VALIDATED = "VALIDATED"                # File video hợp lệ (ffprobe duration, codec)
    INTENT_CREATED = "INTENT_CREATED"      # Đã tạo intent trên UCircle (có video_id)
    PROVISIONED = "PROVISIONED"            # Đã nhận Signed Upload URL
    UPLOADING = "UPLOADING"                # Đang truyền dữ liệu file nhị phân
    PROCESSING = "PROCESSING"              # Upload hoàn tất (HTTP 2xx), xóa file tạm, chờ encode
    ENCODED = "ENCODED"                    # Video đã được hệ thống UCircle xử lý xong
    UNDER_REVIEW = "UNDER_REVIEW"          # Chờ kiểm duyệt nội dung
    PUBLISHED = "PUBLISHED"                # Video đã xuất hiện công khai trên Wavee

    # Trạng thái kết thúc (Terminal states)
    DUPLICATE = "DUPLICATE"                # Video đã tồn tại trong lịch sử
    BLOCKED_POLICY = "BLOCKED_POLICY"      # Vượt trần thời lượng hoặc dung lượng / quota
    BLOCKED_MODERATION = "BLOCKED_MODERATION"  # Bị từ chối kiểm duyệt
    FAILED_PERMANENT = "FAILED_PERMANENT"  # Lỗi không thể phục hồi (link hỏng, v.v.)
    CANCELLED = "CANCELLED"                # Người dùng hủy bỏ

    # Trạng thái chờ retry
    RETRY_WAIT = "RETRY_WAIT"              # Lỗi mạng / rate-limit tạm thời, chờ thử lại


class RightsBasis(str, Enum):
    """Cơ sở pháp lý / quyền sử dụng nội dung."""

    OWNER = "owner"                        # Nội dung do chính người vận hành sở hữu
    LICENSED = "licensed"                  # Nội dung đã mua bản quyền / cấp phép
    CREATOR_OAUTH = "creator_oauth"        # Creator đã cấp quyền qua OAuth
    MANUAL_APPROVAL = "manual_approval"    # Đã duyệt thủ công từng video
