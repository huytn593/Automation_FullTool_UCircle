import hashlib
from pathlib import Path
from typing import List


import re


def sanitize_tiktok_mentions(text: str) -> str:
    """
    Tự động thay thế mọi từ 'tiktok' hoặc 'tik tok' (cả chữ thường, hoa hay hashtag) thành 'UCircle'.
    Ví dụ:
      #tiktok -> #UCircle
      #tiktokvietnam -> #UCirclevietnam
      xem trên tiktok -> xem trên UCircle
    """
    if not text:
        return ""
    # Thay thế không phân biệt hoa thường
    pattern = re.compile(r'tik\s*tok', re.IGNORECASE)
    return pattern.sub("UCircle", text)


def build_caption(title: str, tags: List[str], max_length: int = 2200) -> str:
    """
    Chuẩn hóa tiêu đề và danh sách hashtag thành caption Wavee phù hợp (tối đa 2200 ký tự).
    Tự động thay thế từ khóa TikTok thành UCircle.
    """
    clean_title = (title or "").strip()
    
    # Chuẩn hóa tags: bỏ ký tự # thừa nếu có
    formatted_tags = []
    for tag in tags:
        tag_str = tag.strip().lstrip("#")
        if tag_str and f"#{tag_str}" not in formatted_tags:
            formatted_tags.append(f"#{tag_str}")

    tag_line = " ".join(formatted_tags)
    
    if clean_title and tag_line:
        full_text = f"{clean_title}\n\n{tag_line}"
    elif clean_title:
        full_text = clean_title
    else:
        full_text = tag_line

    # Thay thế toàn bộ từ khóa tiktok -> UCircle
    full_text = sanitize_tiktok_mentions(full_text)

    if len(full_text) > max_length:
        full_text = full_text[: max_length - 3] + "..."

    return full_text


def compute_sha256(file_path: Path) -> str:
    """Tính mã băm SHA-256 của file để phục vụ deduplication và audit."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()
