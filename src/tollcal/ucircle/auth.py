import json
import threading
import time
from pathlib import Path
from typing import Optional
import httpx

from tollcal.config import settings
from tollcal.domain.errors import AuthenticationError, SessionExpiredError
from tollcal.observability.logging import logger
from tollcal.ucircle.models import AuthSession


class AuthManager:
    """Quản lý xác thực Supabase Auth cho tài khoản UCircle."""

    def __init__(self, session_cache_path: Optional[Path] = None):
        self.supabase_url = settings.supabase_url.rstrip("/")
        self.anon_key = settings.supabase_anon_key
        self.email = settings.ucircle_email
        self.password = settings.ucircle_password
        self.session_cache_path = session_cache_path or (settings.data_dir / "session_cache.json")
        self._session: Optional[AuthSession] = None
        self._lock = threading.Lock()

        # Thử nạp session đã lưu trước đó nếu có
        self._load_cached_session()

        # Khởi động thread tự động làm mới token nền
        self._start_auto_refresh()

    def _start_auto_refresh(self) -> None:
        """Khởi động daemon thread tự động refresh token trước khi hết hạn."""
        def _refresh_loop():
            while True:
                time.sleep(20)  # Kiểm tra mỗi 20 giây
                try:
                    with self._lock:
                        # Làm mới nếu token còn dưới 3 phút hiệu lực
                        if self._session and self._session.is_expired(margin_seconds=180):
                            logger.debug("[Auth] Auto-refresh: token sắp hết hạn, đang làm mới sẵn...")
                            self._do_refresh(self._session.refresh_token)
                except Exception as e:
                    logger.debug(f"[Auth] Auto-refresh thất bại (bỏ qua): {e}")

        t = threading.Thread(target=_refresh_loop, daemon=True, name="auth-auto-refresh")
        t.start()
        logger.debug("[Auth] Đã khởi động thread tự động làm mới token nền.")


    def _get_auth_headers(self) -> dict:
        return {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.anon_key}",
            "Content-Type": "application/json;charset=UTF-8",
        }

    def _load_cached_session(self) -> Optional[AuthSession]:
        """Tải session từ file cache cục bộ."""
        if not self.session_cache_path.exists():
            return None
        try:
            with open(self.session_cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                session = AuthSession(**data)
                self._session = session
                logger.debug(f"[Auth] Đã khôi phục phiên làm việc cho user: {session.user_id}")
                return session
        except Exception as e:
            logger.debug(f"[Auth] Không thể nạp session cache: {e}")
            return None

    def _save_cached_session(self, session: AuthSession) -> None:
        """Lưu session vào file cache cục bộ."""
        try:
            self.session_cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.session_cache_path, "w", encoding="utf-8") as f:
                json.dump(session.model_dump(), f, indent=2)
        except Exception as e:
            logger.warning(f"[Auth] Không thể lưu session cache: {e}")

    def send_otp(self, email: Optional[str] = None) -> bool:
        """Gửi mã xác thực OTP về Email của người dùng."""
        target_email = email or self.email
        if not target_email or target_email == "your_email@example.com":
            raise AuthenticationError("Vui lòng cung cấp địa chỉ Email hợp lệ.")

        url = f"{self.supabase_url}/auth/v1/otp"
        payload = {"email": target_email, "create_user": False}

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, headers=self._get_auth_headers(), json=payload)
                if res.status_code not in (200, 201, 204):
                    error_msg = res.json().get("error_description") or res.json().get("msg") or res.text
                    logger.error(f"[Auth] Gửi OTP thất bại ({res.status_code}): {error_msg}")
                    raise AuthenticationError(f"Gửi mã OTP thất bại: {error_msg}")
                logger.info(f"[green]✔ Đã gửi mã xác thực OTP tới email:[/green] [bold]{target_email}[/bold]")
                return True
        except httpx.RequestError as e:
            raise AuthenticationError(f"Lỗi kết nối khi gửi OTP: {e}")

    def verify_otp(self, email: str, token: str) -> AuthSession:
        """Xác thực mã OTP để lấy Access Token và Refresh Token dài hạn."""
        clean_email = email.strip()
        clean_token = token.strip()

        url = f"{self.supabase_url}/auth/v1/verify"
        payload = {"type": "email", "email": clean_email, "token": clean_token}

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, headers=self._get_auth_headers(), json=payload)
                if res.status_code != 200:
                    payload["type"] = "magiclink"
                    res = client.post(url, headers=self._get_auth_headers(), json=payload)
                    if res.status_code != 200:
                        error_msg = res.json().get("error_description") or res.json().get("msg") or res.text
                        logger.error(f"[Auth] Xác thực OTP thất bại ({res.status_code}): {error_msg}")
                        raise AuthenticationError(f"Mã OTP không hợp lệ hoặc đã hết hạn: {error_msg}")

                data = res.json()
                expires_in = data.get("expires_in", 3600)
                expires_at = int(time.time()) + expires_in
                user = data.get("user", {})

                session = AuthSession(
                    access_token=data["access_token"],
                    refresh_token=data["refresh_token"],
                    token_type=data.get("token_type", "bearer"),
                    expires_in=expires_in,
                    expires_at=expires_at,
                    user_id=user.get("id", ""),
                    email=user.get("email", clean_email),
                )
                self._session = session
                self._save_cached_session(session)
                logger.info(f"[green]✔ Đăng nhập OTP thành công![/green] User ID: [bold]{session.user_id}[/bold]")
                return session
        except httpx.RequestError as e:
            raise AuthenticationError(f"Lỗi mạng khi xác thực OTP: {e}")

    def login(self) -> AuthSession:
        """Đăng nhập: Khôi phục từ Cache/Refresh Token hoặc nạp lại từ ổ đĩa."""
        if not self._session:
            self._load_cached_session()

        if self._session and not self._session.is_expired():
            return self._session

        if self._session and self._session.refresh_token:
            try:
                return self._do_refresh(self._session.refresh_token)
            except Exception as e:
                logger.warning(f"[Auth] Không thể làm mới token: {e}")

        raise AuthenticationError(
            "Chưa có phiên làm việc UCircle hợp lệ. Vui lòng xác thực mã OTP: py -3.13 main.py login"
        )

    def _do_refresh(self, refresh_token: str) -> AuthSession:
        """Thực hiện HTTP call để làm mới token — KHÔNG gọi login() để tránh đệ quy."""
        url = f"{self.supabase_url}/auth/v1/token?grant_type=refresh_token"
        payload = {"refresh_token": refresh_token}

        with httpx.Client(timeout=15.0) as client:
            res = client.post(url, headers=self._get_auth_headers(), json=payload)
            if res.status_code != 200:
                logger.warning("[Auth] Refresh token thất bại. Vui lòng đăng nhập lại: py -3.13 main.py login")
                raise AuthenticationError("Phiên đăng nhập đã hết hạn. Vui lòng nhập lại mã OTP.")

            data = res.json()
            expires_in = data.get("expires_in", 3600)
            expires_at = int(time.time()) + expires_in
            user = data.get("user", {})

            session = AuthSession(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", refresh_token),
                token_type=data.get("token_type", "bearer"),
                expires_in=expires_in,
                expires_at=expires_at,
                user_id=user.get("id", self._session.user_id if self._session else ""),
                email=user.get("email", self._session.email if self._session else ""),
            )
            self._session = session
            self._save_cached_session(session)
            logger.debug("[Auth] Đã làm mới Access Token thành công.")
            return session

    def refresh_token(self) -> AuthSession:
        """Làm mới Access Token khi token cũ hết hạn (thread-safe)."""
        with self._lock:
            # Double-check: thread khác có thể đã refresh xong trước khi thread này vào được lock
            if self._session and not self._session.is_expired(margin_seconds=30):
                return self._session
            if not self._session or not self._session.refresh_token:
                raise AuthenticationError("Không có refresh_token để làm mới phiên làm việc.")
            return self._do_refresh(self._session.refresh_token)


    def get_valid_token(self) -> str:
        """Lấy Access Token hợp lệ, tự động refresh nếu token sắp hết hạn."""
        with self._lock:
            if not self._session or self._session.is_expired(margin_seconds=90):
                self.login()
            return self._session.access_token

    def get_user_id(self) -> str:
        """Lấy User ID của tài khoản đang đăng nhập."""
        with self._lock:
            if not self._session:
                self.login()
            return self._session.user_id
