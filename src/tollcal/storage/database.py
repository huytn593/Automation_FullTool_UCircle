import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from tollcal.config import settings


def get_db_path() -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "tollcal.db"


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Tạo kết nối tới SQLite Database với chế độ WAL chống lock và hỗ trợ Row mapping."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database() -> None:
    """Tạo các bảng cơ sở dữ liệu nếu chưa tồn tại và tự động migrate schema."""
    with get_db_connection() as conn:
        # Kiểm tra xem sync_jobs có dính UNIQUE constraint cũ không và migrate
        try:
            schema_info = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sync_jobs';").fetchone()
            if schema_info and "UNIQUE" in schema_info[0].upper():
                conn.executescript("""
                CREATE TABLE IF NOT EXISTS sync_jobs_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_provider TEXT NOT NULL,
                    source_video_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    target_account_id TEXT NOT NULL,
                    rights_basis TEXT NOT NULL DEFAULT 'owner',
                    state TEXT NOT NULL DEFAULT 'DISCOVERED',
                    ucircle_video_id TEXT,
                    caption TEXT DEFAULT '',
                    visibility TEXT DEFAULT 'public',
                    circle_id TEXT,
                    duration_seconds REAL DEFAULT 0.0,
                    file_size_bytes INTEGER DEFAULT 0,
                    sha256_hash TEXT,
                    attempt_count INTEGER DEFAULT 0,
                    next_retry_at TIMESTAMP,
                    error_code TEXT,
                    error_message TEXT,
                    download_latency_ms INTEGER DEFAULT 0,
                    upload_latency_ms INTEGER DEFAULT 0,
                    encode_latency_ms INTEGER DEFAULT 0,
                    total_latency_ms INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    published_at TIMESTAMP
                );
                INSERT INTO sync_jobs_new SELECT * FROM sync_jobs;
                DROP TABLE sync_jobs;
                ALTER TABLE sync_jobs_new RENAME TO sync_jobs;
                """)
        except Exception:
            pass

        conn.executescript("""
        CREATE TABLE IF NOT EXISTS sync_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_provider TEXT NOT NULL,
            source_video_id TEXT NOT NULL,
            source_url TEXT NOT NULL,
            target_account_id TEXT NOT NULL,
            rights_basis TEXT NOT NULL DEFAULT 'owner',
            state TEXT NOT NULL DEFAULT 'DISCOVERED',
            ucircle_video_id TEXT,
            caption TEXT DEFAULT '',
            visibility TEXT DEFAULT 'public',
            circle_id TEXT,
            duration_seconds REAL DEFAULT 0.0,
            file_size_bytes INTEGER DEFAULT 0,
            sha256_hash TEXT,
            attempt_count INTEGER DEFAULT 0,
            next_retry_at TIMESTAMP,
            error_code TEXT,
            error_message TEXT,
            download_latency_ms INTEGER DEFAULT 0,
            upload_latency_ms INTEGER DEFAULT 0,
            encode_latency_ms INTEGER DEFAULT 0,
            total_latency_ms INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_sync_jobs_state ON sync_jobs(state);
        CREATE INDEX IF NOT EXISTS idx_sync_jobs_ucircle_id ON sync_jobs(ucircle_video_id);

        CREATE TABLE IF NOT EXISTS monitored_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_url TEXT NOT NULL UNIQUE,
            creator_id TEXT NOT NULL,
            rights_basis TEXT NOT NULL DEFAULT 'owner',
            is_active INTEGER DEFAULT 1,
            check_interval_minutes INTEGER DEFAULT 30,
            last_scanned_at TIMESTAMP,
            last_video_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
