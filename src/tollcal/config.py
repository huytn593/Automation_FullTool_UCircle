import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Cấu hình toàn hệ thống Tollcal đọc từ biến môi trường hoặc file .env."""

    # UCircle Supabase Auth & Config
    ucircle_email: str = Field(default="", description="Email đăng nhập UCircle")
    ucircle_password: str = Field(default="", description="Mật khẩu đăng nhập UCircle")
    ucircle_base_url: str = Field(default="https://ucircle.net", description="Base URL UCircle")
    supabase_url: str = Field(
        default="https://kkhhpecofolmrodyeslp.supabase.co",
        description="URL Supabase Project của UCircle",
    )
    supabase_anon_key: str = Field(
        default="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtraGhwZWNvZm9sbXJvZHllc2xwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI5ODY1NTIsImV4cCI6MjA4ODU2MjU1Mn0.90c8I1OSw5Zt0-Uu_ZKFuMSbM3PJIDDabosVKhIgQ14",
        description="Anon public key Supabase của UCircle",
    )

    # Sync Configuration
    default_visibility: str = Field(default="public", description="public hoặc connections")
    default_circle_id: Optional[str] = Field(default=None, description="Circle ID nếu muốn gắn vào Circle")
    max_video_duration_seconds: int = Field(default=120, description="Thời lượng video tối đa (mặc định 120s / 2 phút)")
    
    # Path Configuration
    temp_dir: Path = Field(default=Path("./temp"), description="Thư mục chứa video tạm")
    data_dir: Path = Field(default=Path("./data"), description="Thư mục chứa database SQLite")
    csv_export_path: str = Field(default="./lich_su_{date}.csv", description="Đường dẫn file CSV lưu lịch sử (hỗ trợ {date})")
    
    # Scheduler
    auto_sync_interval_minutes: int = Field(default=30, description="Chu kỳ quét kênh (phút)")
    log_level: str = Field(default="INFO", description="Mức độ ghi log")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def ensure_directories(self) -> None:
        """Tạo các thư mục cần thiết nếu chưa tồn tại."""
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)


# Khởi tạo singleton cấu hình
settings = Settings()
settings.ensure_directories()
