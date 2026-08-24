import shutil
from pathlib import Path
from typing import List
from tollcal.domain.errors import MediaValidationError
from tollcal.domain.models import SourceVideo
from tollcal.media.probe import probe_media
from tollcal.sources.base import SourceAdapter


class LocalFileAdapter(SourceAdapter):
    """Adapter xử lý nguồn là file video có sẵn trên ổ đĩa máy tính."""

    def extract_metadata(self, source_path_str: str) -> SourceVideo:
        path = Path(source_path_str)
        if not path.exists():
            raise MediaValidationError(f"File không tồn tại: {path}")

        meta = probe_media(path)
        video_id = path.stem

        return SourceVideo(
            provider="local",
            video_id=video_id,
            source_url=str(path.absolute()),
            title=path.stem,
            tags=[],
            creator_id="local_user",
            creator_name="Local User",
            duration=meta["duration"],
            width=meta["width"],
            height=meta["height"],
            file_size_bytes=meta["file_size"],
            file_path=path,
        )

    def download_video(self, source_path_str: str, output_path: Path) -> SourceVideo:
        path = Path(source_path_str)
        if not path.exists():
            raise MediaValidationError(f"File không tồn tại: {path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, output_path)

        meta = probe_media(output_path)
        return SourceVideo(
            provider="local",
            video_id=output_path.stem,
            source_url=str(path.absolute()),
            title=path.stem,
            tags=[],
            creator_id="local_user",
            creator_name="Local User",
            duration=meta["duration"],
            width=meta["width"],
            height=meta["height"],
            file_size_bytes=meta["file_size"],
            file_path=output_path,
        )

    def list_channel_videos(self, channel_url: str, limit: int = 5) -> List[SourceVideo]:
        return []
