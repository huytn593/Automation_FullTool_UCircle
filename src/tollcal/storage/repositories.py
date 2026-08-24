from datetime import datetime
from typing import List, Optional
from tollcal.domain.models import ChannelMonitor, SyncJob
from tollcal.domain.states import JobState, RightsBasis
from tollcal.storage.database import get_db_connection


class JobRepository:
    """Repository quản lý các bản ghi SyncJob."""

    @staticmethod
    def get_by_id(job_id: int) -> Optional[SyncJob]:
        """Lấy SyncJob theo primary key id."""
        with get_db_connection() as conn:
            cur = conn.execute("SELECT * FROM sync_jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            if row:
                return SyncJob(**dict(row))
        return None

    @staticmethod
    def get_by_source_id(
        provider: str,
        source_video_id: str,
        target_account_id: str,
        circle_id: Optional[str] = None,
    ) -> Optional[SyncJob]:
        with get_db_connection() as conn:
            if circle_id:
                cur = conn.execute(
                    """
                    SELECT * FROM sync_jobs 
                    WHERE source_provider = ? AND source_video_id = ? AND target_account_id = ? AND circle_id = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (provider, source_video_id, target_account_id, circle_id),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT * FROM sync_jobs 
                    WHERE source_provider = ? AND source_video_id = ? AND target_account_id = ? AND (circle_id IS NULL OR circle_id = '')
                    ORDER BY id DESC LIMIT 1
                    """,
                    (provider, source_video_id, target_account_id),
                )
            row = cur.fetchone()
            if row:
                return SyncJob(**dict(row))
        return None

    @staticmethod
    def create_or_get(job: SyncJob) -> SyncJob:
        with get_db_connection() as conn:
            # Kiểm tra xem đã tồn tại trên cùng 1 circle chưa
            existing = JobRepository.get_by_source_id(
                job.source_provider, job.source_video_id, job.target_account_id, job.circle_id
            )
            if existing:
                if existing.state in (JobState.PUBLISHED, JobState.ENCODED, JobState.PROCESSING):
                    return existing
                # Cập nhật lại bản ghi cũ sang trạng thái mới để chạy lại
                conn.execute(
                    """
                    UPDATE sync_jobs
                    SET state = ?, caption = ?, visibility = ?, circle_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (job.state.value, job.caption, job.visibility, job.circle_id, datetime.utcnow(), existing.id),
                )
                existing.state = job.state
                existing.caption = job.caption
                existing.visibility = job.visibility
                existing.circle_id = job.circle_id
                return existing

            cur = conn.execute(
                """
                INSERT INTO sync_jobs (
                    source_provider, source_video_id, source_url, target_account_id,
                    rights_basis, state, ucircle_video_id, caption, visibility,
                    circle_id, duration_seconds, file_size_bytes, sha256_hash,
                    attempt_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.source_provider,
                    job.source_video_id,
                    job.source_url,
                    job.target_account_id,
                    job.rights_basis.value,
                    job.state.value,
                    job.ucircle_video_id,
                    job.caption,
                    job.visibility,
                    job.circle_id,
                    job.duration_seconds,
                    job.file_size_bytes,
                    job.sha256_hash,
                    job.attempt_count,
                    datetime.utcnow(),
                    datetime.utcnow(),
                ),
            )
            job.id = cur.lastrowid
            return job

    @staticmethod
    def update_state(
        job_id: int,
        state: JobState,
        ucircle_video_id: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        published_at: Optional[datetime] = None,
    ) -> None:
        with get_db_connection() as conn:
            conn.execute(
                """
                UPDATE sync_jobs
                SET state = ?,
                    ucircle_video_id = COALESCE(?, ucircle_video_id),
                    error_code = ?,
                    error_message = ?,
                    published_at = COALESCE(?, published_at),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    state.value,
                    ucircle_video_id,
                    error_code,
                    error_message,
                    published_at,
                    datetime.utcnow(),
                    job_id,
                ),
            )

    @staticmethod
    def update_metrics(
        job_id: int,
        duration_seconds: float,
        file_size_bytes: int,
        sha256_hash: Optional[str] = None,
        download_latency_ms: int = 0,
        upload_latency_ms: int = 0,
        encode_latency_ms: int = 0,
        total_latency_ms: int = 0,
    ) -> None:
        with get_db_connection() as conn:
            conn.execute(
                """
                UPDATE sync_jobs
                SET duration_seconds = ?,
                    file_size_bytes = ?,
                    sha256_hash = COALESCE(?, sha256_hash),
                    download_latency_ms = ?,
                    upload_latency_ms = ?,
                    encode_latency_ms = ?,
                    total_latency_ms = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    duration_seconds,
                    file_size_bytes,
                    sha256_hash,
                    download_latency_ms,
                    upload_latency_ms,
                    encode_latency_ms,
                    total_latency_ms,
                    datetime.utcnow(),
                    job_id,
                ),
            )

    @staticmethod
    def list_jobs(limit: int = 50) -> List[SyncJob]:
        with get_db_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM sync_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [SyncJob(**dict(row)) for row in cur.fetchall()]


class ChannelRepository:
    """Repository quản lý cấu hình các kênh Creator."""

    @staticmethod
    def add_channel(channel_url: str, creator_id: str, rights_basis: RightsBasis) -> ChannelMonitor:
        with get_db_connection() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO monitored_channels (
                    channel_url, creator_id, rights_basis, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (channel_url, creator_id, rights_basis.value, datetime.utcnow()),
            )
            return ChannelMonitor(
                id=cur.lastrowid,
                channel_url=channel_url,
                creator_id=creator_id,
                rights_basis=rights_basis,
            )

    @staticmethod
    def list_active_channels() -> List[ChannelMonitor]:
        with get_db_connection() as conn:
            cur = conn.execute("SELECT * FROM monitored_channels WHERE is_active = 1")
            return [ChannelMonitor(**dict(row)) for row in cur.fetchall()]

    @staticmethod
    def update_scan_status(channel_id: int, last_video_id: Optional[str]) -> None:
        with get_db_connection() as conn:
            conn.execute(
                """
                UPDATE monitored_channels
                SET last_scanned_at = ?,
                    last_video_id = COALESCE(?, last_video_id)
                WHERE id = ?
                """,
                (datetime.utcnow(), last_video_id, channel_id),
            )
