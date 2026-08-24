import hashlib
import json
import os
import config


def _ensure_db():
    os.makedirs(os.path.dirname(config.POSTED_HASH_DB_PATH), exist_ok=True)
    if not os.path.exists(config.POSTED_HASH_DB_PATH):
        with open(config.POSTED_HASH_DB_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)


def load_posted_set() -> set:
    _ensure_db()
    with open(config.POSTED_HASH_DB_PATH, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_posted_set(posted_set: set):
    with open(config.POSTED_HASH_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(posted_set), f, ensure_ascii=False, indent=2)


def is_file_posted(file_path: str) -> bool:
    if not os.path.exists(file_path):
        return False
    posted = load_posted_set()
    file_hash = get_file_hash(file_path)
    return file_hash in posted


def mark_file_as_posted(file_path: str):
    posted = load_posted_set()
    file_hash = get_file_hash(file_path)
    posted.add(file_hash)
    save_posted_set(posted)


def get_file_hash(file_path: str) -> str:
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()
