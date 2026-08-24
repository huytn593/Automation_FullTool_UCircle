from typing import Optional


class TollcalError(Exception):
    """Lớp Exception cơ sở của hệ thống Tollcal."""

    def __init__(self, message: str, code: str = "GENERIC_ERROR", is_retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.is_retryable = is_retryable

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# --- Nhóm lỗi xác thực & tài khoản ---

class AuthenticationError(TollcalError):
    """Lỗi đăng nhập hoặc sai thông tin xác thực."""
    def __init__(self, message: str = "Đăng nhập UCircle thất bại. Vui lòng kiểm tra email/password."):
        super().__init__(message, code="AUTH_FAILED", is_retryable=False)


class SessionExpiredError(TollcalError):
    """Phiên đăng nhập hết hạn và không thể refresh."""
    def __init__(self, message: str = "Phiên làm việc hết hạn."):
        super().__init__(message, code="SESSION_EXPIRED", is_retryable=True)


# --- Nhóm lỗi Hạn mức & Chính sách ---

class QuotaExceededError(TollcalError):
    """Hết hạn mức lưu trữ hoặc số phút video Wavee."""
    def __init__(self, message: str = "Tài khoản UCircle đã hết hạn mức upload Wavee."):
        super().__init__(message, code="QUOTA_EXCEEDED", is_retryable=False)


class VideoTooLongError(TollcalError):
    """Thời lượng video vượt quá giới hạn cho phép."""
    def __init__(self, duration: float, max_allowed: float):
        super().__init__(
            f"Thời lượng video ({duration:.1f}s) vượt quá giới hạn tài khoản ({max_allowed:.1f}s).",
            code="VIDEO_TOO_LONG",
            is_retryable=False,
        )


class VideoTooLargeError(TollcalError):
    """Dung lượng file vượt quá giới hạn cho phép."""
    def __init__(self, size_mb: float, max_mb: float):
        super().__init__(
            f"Dung lượng video ({size_mb:.1f}MB) vượt quá giới hạn ({max_mb:.1f}MB).",
            code="VIDEO_TOO_LARGE",
            is_retryable=False,
        )


# --- Nhóm lỗi Nguồn video (TikTok/Local) ---

class SourceExtractionError(TollcalError):
    """Lỗi khi tải hoặc trích xuất link TikTok."""
    def __init__(self, message: str, is_retryable: bool = True):
        super().__init__(message, code="SOURCE_EXTRACT_ERROR", is_retryable=is_retryable)


class SourceNotFoundError(TollcalError):
    """Video nguồn đã bị xóa hoặc ở chế độ riêng tư."""
    def __init__(self, message: str = "Video nguồn không tồn tại hoặc đã bị ẩn/xóa."):
        super().__init__(message, code="SOURCE_NOT_FOUND", is_retryable=False)


class MediaValidationError(TollcalError):
    """File tải về bị hỏng hoặc không phải định dạng video tương thích."""
    def __init__(self, message: str):
        super().__init__(message, code="MEDIA_INVALID", is_retryable=False)


# --- Nhóm lỗi Upload & API UCircle ---

class UploadProvisionError(TollcalError):
    """Lỗi khi xin URL Signed Upload từ UCircle."""
    def __init__(self, message: str, is_retryable: bool = True):
        super().__init__(message, code="PROVISION_FAILED", is_retryable=is_retryable)


class BinaryUploadError(TollcalError):
    """Lỗi mạng trong lúc gửi stream file video lên server."""
    def __init__(self, message: str, is_retryable: bool = True):
        super().__init__(message, code="UPLOAD_FAILED", is_retryable=is_retryable)


class VideoEncodingTimeoutError(TollcalError):
    """Quá thời gian chờ hệ thống UCircle encode video."""
    def __init__(self, video_id: str, timeout_seconds: int):
        super().__init__(
            f"Quá thời gian chờ encode video {video_id} ({timeout_seconds}s).",
            code="ENCODE_TIMEOUT",
            is_retryable=True,
        )


class DuplicateJobError(TollcalError):
    """Video đã được đồng bộ trước đó."""
    def __init__(self, source_id: str):
        super().__init__(
            f"Video với ID {source_id} đã tồn tại trong hệ thống, bỏ qua để tránh trùng lặp.",
            code="DUPLICATE_VIDEO",
            is_retryable=False,
        )
