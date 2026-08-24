import os
import time
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List
import httpx

from tollcal.config import settings
from tollcal.domain.errors import (
    BinaryUploadError,
    QuotaExceededError,
    TollcalError,
    UploadProvisionError,
    VideoEncodingTimeoutError,
)
from tollcal.domain.models import UploadIntent, WaveeCaps
from tollcal.observability.logging import logger
from tollcal.ucircle.auth import AuthManager
from tollcal.ucircle.models import ProvisionResponse


# Singleton AuthManager shared across all UCircleClient instances
# to prevent race conditions when multiple concurrent requests try
# to refresh the same Supabase token simultaneously.
_shared_auth_manager: Optional[AuthManager] = None


def _get_shared_auth_manager() -> AuthManager:
    global _shared_auth_manager
    if _shared_auth_manager is None:
        _shared_auth_manager = AuthManager()
    return _shared_auth_manager


class UCircleClient:
    """Client giao tiếp trực tiếp với các RPC và HTTP Endpoints của UCircle."""

    def __init__(self, auth_manager: Optional[AuthManager] = None):
        self.auth = auth_manager or _get_shared_auth_manager()
        self.supabase_url = settings.supabase_url.rstrip("/")
        self.anon_key = settings.supabase_anon_key
        self.base_url = settings.ucircle_base_url.rstrip("/")

    def _get_headers(self, custom_token: Optional[str] = None) -> dict:
        token = custom_token or self.auth.get_valid_token()
        return {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _rpc(self, rpc_name: str, payload: Dict[str, Any] = None) -> Any:
        """Thực thi một Supabase RPC function (Tự động refresh token nếu JWT expired)."""
        url = f"{self.supabase_url}/rest/v1/rpc/{rpc_name}"
        headers = self._get_headers()
        payload = payload or {}

        with httpx.Client(timeout=25.0) as client:
            res = client.post(url, headers=headers, json=payload)
            
            # Nếu gặp lỗi 401 hoặc JWT expired -> tự động refresh token và thử lại ngay 1 lần
            if res.status_code == 401 or "jwt expired" in res.text.lower() or "invalid claim" in res.text.lower():
                logger.info("[UCircle] Access Token hết hạn (JWT expired). Đang tự động làm mới token...")
                try:
                    self.auth.refresh_token()
                    headers = self._get_headers()
                    res = client.post(url, headers=headers, json=payload)
                except Exception as rf_err:
                    logger.warning(f"[UCircle] Không thể tự làm mới token: {rf_err}")

            if res.status_code not in (200, 201, 204):
                error_body = res.text
                try:
                    err_json = res.json()
                    error_msg = err_json.get("message") or err_json.get("error") or error_body
                except Exception:
                    error_msg = error_body
                logger.error(f"[UCircle RPC] Lỗi gọi {rpc_name} ({res.status_code}): {error_msg}")
                raise TollcalError(f"RPC {rpc_name} failed: {error_msg}", code=f"RPC_{res.status_code}")
            
            if res.status_code == 204 or not res.text.strip():
                return None
            return res.json()

    def get_caps(self) -> WaveeCaps:
        """Lấy hạn mức tài khoản Wavee (hạn mức thời lượng, dung lượng, số phút còn lại)."""
        try:
            data = self._rpc("rpc_ucircle_wavee_caps_self", {})
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            if not isinstance(data, dict):
                data = {}

            caps = WaveeCaps(
                tier=data.get("tier", "standard"),
                max_seconds=float(data.get("max_seconds", settings.max_video_duration_seconds)),
                max_mb=float(data.get("max_mb", 250.0)),
                quota_minutes_cap=data.get("quota_minutes_cap"),
                quota_minutes_used=data.get("quota_minutes_used"),
                quota_minutes_remaining=data.get("quota_minutes_remaining"),
            )
            return caps
        except Exception as e:
            logger.warning(f"[UCircle] Không thể đọc caps từ server: {e}. Dùng cấu hình mặc định.")
            return WaveeCaps(max_seconds=settings.max_video_duration_seconds)

    def list_my_circles(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các Circles mà tài khoản này tham gia hoặc sở hữu."""
        user_id = self.auth.get_user_id()
        circles = []
        headers = self._get_headers()

        # 1. Thử lấy từ REST endpoint circle_members hoặc circles
        try:
            url1 = f"{self.supabase_url}/rest/v1/circle_members?select=circle_id,role,circles(id,name,handle,avatar_url)&user_id=eq.{user_id}"
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url1, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    for item in data:
                        c = item.get("circles")
                        if isinstance(c, dict) and c.get("id"):
                            circles.append({
                                "id": c["id"],
                                "name": c.get("name") or c.get("handle") or c["id"][:8],
                                "handle": c.get("handle") or "",
                                "role": item.get("role", "member"),
                            })
        except Exception as e:
            logger.debug(f"[UCircle] Không thể lấy circles qua circle_members: {e}")

        # 2. Thử lấy từ bảng circles trực tiếp
        if not circles:
            try:
                url2 = f"{self.supabase_url}/rest/v1/circles?select=id,name,handle,avatar_url&owner_id=eq.{user_id}"
                with httpx.Client(timeout=15.0) as client:
                    res = client.get(url2, headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        for c in data:
                            if isinstance(c, dict) and c.get("id"):
                                circles.append({
                                    "id": c["id"],
                                    "name": c.get("name") or c.get("handle") or c["id"][:8],
                                    "handle": c.get("handle") or "",
                                    "role": "owner",
                                })
            except Exception as e:
                logger.debug(f"[UCircle] Không thể lấy circles qua owner_id: {e}")

        return circles

    def create_intent(
        self,
        caption: str = "",
        visibility: str = "public",
        circle_id: Optional[str] = None,
    ) -> UploadIntent:
        """Tạo Intent upload trên UCircle để nhận video_id."""
        # Chuẩn bị payload tương thích với RPC
        payload = {
            "p_caption": caption,
            "p_visibility": visibility,
            "p_circle_id": circle_id if circle_id else None,
        }
        
        try:
            data = self._rpc("rpc_ucircle_wavee_upload_intent", payload)
        except TollcalError as e:
            # Thử lại nếu server dùng tên tham số không có prefix 'p_'
            if "parameter" in str(e).lower() or "not found" in str(e).lower():
                alt_payload = {
                    "caption": caption,
                    "visibility": visibility,
                    "circle_id": circle_id if circle_id else None,
                }
                data = self._rpc("rpc_ucircle_wavee_upload_intent", alt_payload)
            else:
                raise

        if isinstance(data, dict):
            video_id = data.get("video_id") or data.get("id")
        elif isinstance(data, str):
            video_id = data
        else:
            raise TollcalError(f"RPC upload intent trả về định dạng lạ: {data}")

        if not video_id:
            raise TollcalError("Không nhận được video_id từ UCircle upload intent.")

        return UploadIntent(
            video_id=video_id,
            caption=caption,
            visibility=visibility,
            circle_id=circle_id,
        )

    def provision_upload(self, video_id: str) -> ProvisionResponse:
        """Gửi request tới provision endpoint của UCircle để lấy Signed Upload URL."""
        url = f"{self.base_url}/api/v1/ucircle/wavee/provision"
        token = self.auth.get_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"video_id": video_id}

        try:
            with httpx.Client(timeout=25.0) as client:
                res = client.post(url, headers=headers, json=payload)
                if res.status_code == 401 or "jwt expired" in res.text.lower():
                    logger.info("[UCircle Provision] Token hết hạn, đang làm mới và thử lại...")
                    self.auth.refresh_token()
                    headers["Authorization"] = f"Bearer {self.auth.get_valid_token()}"
                    res = client.post(url, headers=headers, json=payload)

                if res.status_code not in (200, 201):
                    raise UploadProvisionError(
                        f"Provision upload thất bại ({res.status_code}): {res.text}"
                    )
                data = res.json()
                upload_url = data.get("upload_url") or data.get("url")
                if not upload_url:
                    raise UploadProvisionError(f"Provision không trả về upload_url: {data}")

                return ProvisionResponse(
                    upload_url=upload_url,
                    video_id=video_id,
                    fields=data.get("fields"),
                )
        except httpx.RequestError as e:
            raise UploadProvisionError(f"Lỗi kết nối tới Provision API: {e}", is_retryable=True)

    def upload_binary(
        self,
        upload_url: str,
        file_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Tải file video lên Signed Upload URL dạng streaming PUT (nhanh hơn multipart)."""
        if not file_path.exists():
            raise BinaryUploadError(f"File video không tồn tại: {file_path}", is_retryable=False)

        file_size = file_path.stat().st_size
        # Timeout: tối thiểu 60s, cộng thêm 1s mỗi MB (giả định ~1 MB/s tối thiểu)
        timeout_sec = max(60.0, file_size / (1024 * 1024))

        def _file_generator(path: Path, buf_size: int = 4 * 1024 * 1024):
            """Generator đọc file theo từng block 4MB để upload streaming."""
            with open(path, "rb", buffering=buf_size) as fh:
                while True:
                    block = fh.read(buf_size)
                    if not block:
                        break
                    yield block

        try:
            with httpx.Client(timeout=timeout_sec) as client:
                # Ưu tiên streaming PUT — nhanh hơn nhiều so với multipart POST
                res = client.put(
                    upload_url,
                    content=_file_generator(file_path),
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(file_size),
                    },
                )
                if res.status_code not in (200, 201, 204):
                    # Fallback: multipart POST nếu server không chấp nhận PUT
                    with open(file_path, "rb") as f:
                        res = client.post(upload_url, files={"file": (file_path.name, f, "video/mp4")})
                    if res.status_code not in (200, 201, 204):
                        raise BinaryUploadError(
                            f"Upload file thất bại (HTTP {res.status_code}): {res.text}"
                        )

            if progress_callback:
                progress_callback(file_size, file_size)

        except httpx.RequestError as e:
            raise BinaryUploadError(f"Lỗi mạng khi upload file video: {e}", is_retryable=True)


    def get_video_status(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Truy vấn bản ghi video từ bảng ucircle_wavee_video để kiểm tra trạng thái encode."""
        url = f"{self.supabase_url}/rest/v1/ucircle_wavee_video?id=eq.{video_id}&select=*"
        headers = self._get_headers()

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 200:
                    rows = res.json()
                    if rows and len(rows) > 0:
                        return rows[0]
            return None
        except Exception as e:
            logger.debug(f"[UCircle] Lỗi khi truy vấn ucircle_wavee_video: {e}")
            return None

    def poll_until_ready(
        self,
        video_id: str,
        timeout_seconds: int = 120,
        interval_seconds: float = 2.5,
    ) -> Dict[str, Any]:
        """Lắng nghe trạng thái encode của video cho đến khi hoàn tất hoặc timeout."""
        start_time = time.time()
        logger.info(f"[UCircle] Bắt đầu polling trạng thái video [bold]{video_id}[/bold]...")

        while time.time() - start_time < timeout_seconds:
            status_data = self.get_video_status(video_id)
            if status_data:
                state = (status_data.get("status") or status_data.get("state") or "").lower()
                is_ready = status_data.get("is_ready") or status_data.get("ready") or False
                
                logger.debug(f"[UCircle Polling] Video {video_id} status: {state}, ready: {is_ready}")

                if is_ready or state in ("encoded", "ready", "published", "active"):
                    logger.info(f"[green]✔ Video {video_id} đã encode thành công![/green]")
                    return status_data
                elif state in ("error", "failed", "rejected"):
                    raise TollcalError(f"Video {video_id} encode thất bại trên server UCircle: {status_data}")

            time.sleep(interval_seconds)

        logger.warning(f"[UCircle] Video {video_id} chưa xong encode sau {timeout_seconds}s (chuyển theo dõi nền).")
        return {"id": video_id, "status": "processing"}
