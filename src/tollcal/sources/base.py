from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional
from tollcal.domain.models import SourceVideo


class SourceAdapter(ABC):
    """Giao diện trừu tượng cho các nguồn video (TikTok, Local File, v.v.)."""

    @abstractmethod
    def extract_metadata(self, source_url: str) -> SourceVideo:
        """Trích xuất metadata mà chưa cần tải file binary."""
        pass

    @abstractmethod
    def download_video(self, source_url: str, output_path: Path) -> SourceVideo:
        """Tải video không watermark về đường dẫn chỉ định."""
        pass

    @abstractmethod
    def list_channel_videos(self, channel_url: str, limit: int = 5) -> List[SourceVideo]:
        """Lấy danh sách các video mới nhất của kênh/creator."""
        pass
