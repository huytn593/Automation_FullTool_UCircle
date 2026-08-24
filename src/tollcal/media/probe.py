import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from tollcal.domain.errors import MediaValidationError
from tollcal.observability.logging import logger


def has_ffprobe() -> bool:
    """Kiểm tra máy có sẵn lệnh ffprobe hay không."""
    return shutil.which("ffprobe") is not None


def probe_media(file_path: Path) -> Dict[str, Any]:
    """
    Sử dụng ffprobe để trích xuất thông số kỹ thuật chi tiết của video:
    - duration (thời lượng)
    - width, height (độ phân giải)
    - video/audio codec
    - file size
    """
    if not file_path.exists():
        raise MediaValidationError(f"File video không tồn tại: {file_path}")

    file_size = file_path.stat().st_size
    if file_size == 0:
        raise MediaValidationError("File video rỗng (0 bytes).")

    if not has_ffprobe():
        logger.debug("[MediaProbe] ffprobe không có trong PATH, sử dụng kích thước file cơ bản.")
        return {
            "duration": 0.0,
            "width": None,
            "height": None,
            "video_codec": None,
            "audio_codec": None,
            "file_size": file_size,
        }

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
        data = json.loads(result.stdout)
        
        format_info = data.get("format", {})
        duration = float(format_info.get("duration", 0.0))

        width = None
        height = None
        v_codec = None
        a_codec = None

        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type")
            if codec_type == "video" and not v_codec:
                v_codec = stream.get("codec_name")
                width = stream.get("width")
                height = stream.get("height")
            elif codec_type == "audio" and not a_codec:
                a_codec = stream.get("codec_name")

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "video_codec": v_codec,
            "audio_codec": a_codec,
            "file_size": file_size,
        }
    except Exception as e:
        logger.warning(f"[MediaProbe] Lỗi khi chạy ffprobe: {e}")
        return {
            "duration": 0.0,
            "width": None,
            "height": None,
            "video_codec": None,
            "audio_codec": None,
            "file_size": file_size,
        }
