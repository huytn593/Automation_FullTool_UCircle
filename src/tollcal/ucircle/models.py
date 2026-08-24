from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AuthSession(BaseModel):
    """Thông tin phiên đăng nhập Supabase Auth."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    expires_at: int
    user_id: str
    email: Optional[str] = None

    def is_expired(self, margin_seconds: int = 60) -> bool:
        """Kiểm tra token đã hết hạn hoặc sắp hết hạn hay chưa."""
        import time
        current_ts = int(time.time())
        return self.expires_at - current_ts < margin_seconds


class ProvisionResponse(BaseModel):
    """URL Upload đã ký nhận từ endpoint provision của UCircle."""

    upload_url: str
    video_id: str
    fields: Optional[dict] = None
