from datetime import datetime
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from tollcal.domain.states import JobState, RightsBasis


class SourceVideo(BaseModel):
    """Thông tin video trích xuất từ nguồn (TikTok hoặc Local)."""

    provider: str = Field(default="tiktok", description="tiktok hoặc local")
    video_id: str = Field(description="ID định danh duy nhất của video trên nguồn")
    source_url: str = Field(description="URL gốc của video")
    title: str = Field(default="", description="Tiêu đề hoặc mô tả của video")
    tags: List[str] = Field(default_factory=list, description="Danh sách hashtags")
    creator_id: str = Field(default="", description="ID hoặc username của tác giả")
    creator_name: str = Field(default="", description="Tên hiển thị tác giả")
    duration: float = Field(default=0.0, description="Thời lượng tính bằng giây")
    width: Optional[int] = None
    height: Optional[int] = None
    file_size_bytes: int = 0
    file_path: Optional[Path] = None
    sha256_hash: Optional[str] = None


class WaveeCaps(BaseModel):
    """Hạn mức tài khoản UCircle Wavee."""

    tier: str = "free"
    max_seconds: float = 180.0
    max_mb: float = 250.0
    quota_minutes_cap: Optional[float] = None
    quota_minutes_used: Optional[float] = None
    quota_minutes_remaining: Optional[float] = None


class UploadIntent(BaseModel):
    """Dữ liệu phản hồi khi tạo Upload Intent trên UCircle."""

    video_id: str
    upload_url: Optional[str] = None
    circle_id: Optional[str] = None
    visibility: str = "public"
    caption: str = ""


class SyncJob(BaseModel):
    """Tiến trình đồng bộ một video từ nguồn sang UCircle."""

    id: Optional[int] = None
    source_provider: str = "tiktok"
    source_video_id: str
    source_url: str
    target_account_id: str
    rights_basis: RightsBasis = RightsBasis.OWNER
    state: JobState = JobState.DISCOVERED
    ucircle_video_id: Optional[str] = None
    caption: str = ""
    visibility: str = "public"
    circle_id: Optional[str] = None
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    sha256_hash: Optional[str] = None
    attempt_count: int = 0
    next_retry_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    download_latency_ms: int = 0
    upload_latency_ms: int = 0
    encode_latency_ms: int = 0
    total_latency_ms: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: Optional[datetime] = None


class ChannelMonitor(BaseModel):
    """Cấu hình theo dõi một kênh creator."""

    id: Optional[int] = None
    channel_url: str
    creator_id: str
    rights_basis: RightsBasis = RightsBasis.OWNER
    is_active: bool = True
    check_interval_minutes: int = 30
    last_scanned_at: Optional[datetime] = None
    last_video_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
