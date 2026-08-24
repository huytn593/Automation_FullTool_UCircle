import os
import uuid
from pathlib import Path
from typing import Generator
from contextlib import contextmanager

from tollcal.config import settings
from tollcal.observability.logging import logger


class TempFileManager:
    """Quản lý vòng đời của các file tạm trong quá trình tải và upload."""

    def __init__(self, temp_dir: Path = None):
        self.temp_dir = temp_dir or settings.temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def create_temp_path(self, prefix: str = "video", extension: str = "mp4") -> Path:
        """Tạo đường dẫn file tạm duy nhất."""
        unique_name = f"{prefix}_{uuid.uuid4().hex[:12]}.{extension}"
        return self.temp_dir / unique_name

    def create_part_path(self, final_path: Path) -> Path:
        """Tạo đường dẫn file .part cho quá trình tải ngắt quãng."""
        return final_path.with_suffix(".part")

    def atomic_rename(self, part_path: Path, final_path: Path) -> None:
        """Đổi tên file .part thành file chính thức sau khi tải xong."""
        if part_path.exists():
            part_path.replace(final_path)

    def delete_file_safe(self, file_path: Path) -> bool:
        """Xóa file tạm an toàn, không báo lỗi nếu file không tồn tại."""
        try:
            if file_path and file_path.exists():
                file_path.unlink()
                logger.debug(f"[TempFiles] Đã xóa file tạm: {file_path.name}")
                return True
        except Exception as e:
            logger.warning(f"[TempFiles] Không thể xóa file tạm {file_path}: {e}")
        return False

    def cleanup_expired_files(self, max_age_seconds: int = 3600) -> int:
        """Dọn dẹp các file rác hoặc file .part bị bỏ lại lâu hơn max_age_seconds."""
        import time
        now = time.time()
        deleted_count = 0
        
        for p in self.temp_dir.glob("*"):
            if p.is_file():
                try:
                    if now - p.stat().st_mtime > max_age_seconds:
                        p.unlink()
                        deleted_count += 1
                except Exception:
                    pass
        return deleted_count


temp_manager = TempFileManager()
