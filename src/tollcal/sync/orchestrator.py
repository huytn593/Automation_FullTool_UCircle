import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from tollcal.config import settings
from tollcal.domain.errors import (
    DuplicateJobError,
    QuotaExceededError,
    TollcalError,
    VideoTooLargeError,
    VideoTooLongError,
)
from tollcal.domain.models import SourceVideo, SyncJob
from tollcal.domain.states import JobState, RightsBasis
from tollcal.media.normalize import build_caption, compute_sha256, sanitize_tiktok_mentions
from tollcal.media.probe import probe_media
from tollcal.media.temp_files import temp_manager
from tollcal.observability.logging import logger
from tollcal.sources.base import SourceAdapter
from tollcal.sources.local_file import LocalFileAdapter
from tollcal.sources.tiktok_ytdlp import TikTokYtDlpAdapter
from tollcal.storage.database import init_database
from tollcal.storage.repositories import JobRepository
from tollcal.sync.dedup import is_already_synced
from tollcal.ucircle.client import UCircleClient


class SyncOrchestrator:
    """Điều phối toàn bộ luồng đồng bộ từ nguồn (TikTok/Local) tới UCircle Wavee."""

    def __init__(
        self,
        ucircle_client: Optional[UCircleClient] = None,
        tiktok_adapter: Optional[SourceAdapter] = None,
        local_adapter: Optional[SourceAdapter] = None,
    ):
        init_database()
        self.ucircle = ucircle_client or UCircleClient()
        self.tiktok = tiktok_adapter or TikTokYtDlpAdapter()
        self.local = local_adapter or LocalFileAdapter()

    def sync_single_video(
        self,
        source_url_or_path: str,
        visibility: str = "public",
        circle_id: Optional[str] = None,
        rights_basis: RightsBasis = RightsBasis.OWNER,
        poll_encode: bool = True,
        custom_caption: Optional[str] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ) -> SyncJob:
        """
        Thực thi đồng bộ 1 video duy nhất theo đầy đủ các bước an toàn:
        1. Nhận diện Adapter (TikTok hoặc Local file).
        2. Đăng nhập & lấy User ID UCircle.
        3. Extract Metadata & Kiểm tra chống trùng lặp.
        4. Tải file video tạm (.part -> .mp4).
        5. Kiểm tra thời lượng / dung lượng so với Quota UCircle.
        6. Tạo Intent trên UCircle -> Lưu video_id vào DB.
        7. Xin Signed URL từ Provision API.
        8. Upload file nhị phân -> HTTP 2xx.
        9. Xóa ngay file tạm trên ổ đĩa.
        10. Poll kiểm tra trạng thái encode (nếu poll_encode=True).
        """
        start_time = time.time()
        logger.info(f"[bold cyan]▶ Bắt đầu tiến trình đồng bộ:[/bold cyan] {source_url_or_path}")

        # 1. Xác định Adapter
        is_local = Path(source_url_or_path).exists()
        adapter: SourceAdapter = self.local if is_local else self.tiktok
        target_circle_id = circle_id or settings.default_circle_id

        # 2. Lấy User ID tài khoản UCircle
        target_account_id = self.ucircle.auth.get_user_id()

        # 3. Trích xuất metadata sơ bộ
        if progress_callback:
            progress_callback("Trích xuất metadata nguồn...", 0.1)
        source_meta = adapter.extract_metadata(source_url_or_path)

        # Kiểm tra chống trùng lặp (Theo từng Circle riêng biệt)
        if is_already_synced(source_meta.provider, source_meta.video_id, target_account_id, target_circle_id):
            logger.warning(
                f"[yellow]⚠ Video {source_meta.video_id} đã tồn tại trong lịch sử đồng bộ của Circle {target_circle_id or 'mặc định'}. Bỏ qua.[/yellow]"
            )
            job = JobRepository.get_by_source_id(source_meta.provider, source_meta.video_id, target_account_id, target_circle_id)
            if job:
                return job
            raise DuplicateJobError(source_meta.video_id)

        # Tạo Job trong DB (Chuẩn hóa & thay thế mọi từ khóa TikTok thành UCircle)
        if custom_caption:
            caption = sanitize_tiktok_mentions(custom_caption)
        else:
            caption = build_caption(source_meta.title, source_meta.tags)
        job = SyncJob(
            source_provider=source_meta.provider,
            source_video_id=source_meta.video_id,
            source_url=source_url_or_path,
            target_account_id=target_account_id,
            rights_basis=rights_basis,
            state=JobState.DISCOVERED,
            caption=caption,
            visibility=visibility,
            circle_id=target_circle_id,
        )
        job = JobRepository.create_or_get(job)

        temp_video_path: Optional[Path] = None
        try:
            # 4. Tải file video về thư mục tạm
            JobRepository.update_state(job.id, JobState.DOWNLOADING)
            if progress_callback:
                progress_callback("Đang tải video về máy tạm...", 0.25)
            
            dl_start = time.time()
            temp_video_path = temp_manager.create_temp_path(prefix=f"sync_{source_meta.video_id}")
            downloaded_video = adapter.download_video(source_url_or_path, temp_video_path)
            dl_latency = int((time.time() - dl_start) * 1000)

            # 5. Phân tích & Kiểm tra kỹ thuật (ffprobe, sha256)
            JobRepository.update_state(job.id, JobState.VALIDATED)
            if progress_callback:
                progress_callback("Kiểm tra thông số kỹ thuật video...", 0.45)
            
            media_info = probe_media(temp_video_path)
            actual_duration = media_info["duration"] or downloaded_video.duration
            actual_size = temp_video_path.stat().st_size
            sha256 = compute_sha256(temp_video_path)

            # Đọc hạn mức tài khoản UCircle
            caps = self.ucircle.get_caps()
            if actual_duration > caps.max_seconds:
                JobRepository.update_state(
                    job.id, JobState.BLOCKED_POLICY, error_code="VIDEO_TOO_LONG",
                    error_message=f"Thời lượng {actual_duration:.1f}s > hạn mức {caps.max_seconds:.1f}s"
                )
                raise VideoTooLongError(actual_duration, caps.max_seconds)

            size_mb = actual_size / (1024 * 1024)
            if size_mb > caps.max_mb:
                JobRepository.update_state(
                    job.id, JobState.BLOCKED_POLICY, error_code="VIDEO_TOO_LARGE",
                    error_message=f"Dung lượng {size_mb:.1f}MB > hạn mức {caps.max_mb:.1f}MB"
                )
                raise VideoTooLargeError(size_mb, caps.max_mb)

            # 6. Tạo Intent trên UCircle
            JobRepository.update_state(job.id, JobState.INTENT_CREATED)
            if progress_callback:
                progress_callback("Tạo Upload Intent trên UCircle...", 0.6)
            
            intent = self.ucircle.create_intent(
                caption=caption,
                visibility=visibility,
                circle_id=target_circle_id,
            )
            ucircle_video_id = intent.video_id
            JobRepository.update_state(job.id, JobState.INTENT_CREATED, ucircle_video_id=ucircle_video_id)
            logger.info(f"[UCircle] Đã tạo Intent thành công, video_id: [bold]{ucircle_video_id}[/bold]")

            # 7. Xin Signed Upload URL
            JobRepository.update_state(job.id, JobState.PROVISIONED)
            if progress_callback:
                progress_callback("Nhận URL Upload có chữ ký...", 0.7)
            
            provision = self.ucircle.provision_upload(ucircle_video_id)

            # 8. Upload file nhị phân
            JobRepository.update_state(job.id, JobState.UPLOADING)
            if progress_callback:
                progress_callback("Đang truyền file video lên UCircle...", 0.8)
            
            up_start = time.time()
            self.ucircle.upload_binary(provision.upload_url, temp_video_path)
            up_latency = int((time.time() - up_start) * 1000)
            logger.info(f"[green]✔ Upload binary thành công trong {up_latency}ms![/green]")

            # 9. Xóa ngay file tạm trên ổ đĩa sau khi upload thành công
            JobRepository.update_state(job.id, JobState.PROCESSING)
            temp_manager.delete_file_safe(temp_video_path)
            temp_video_path = None

            # 10. Polling trạng thái encode
            encode_latency = 0
            if poll_encode:
                if progress_callback:
                    progress_callback("Đang chờ server UCircle xử lý & encode video...", 0.9)
                enc_start = time.time()
                self.ucircle.poll_until_ready(ucircle_video_id)
                encode_latency = int((time.time() - enc_start) * 1000)
                JobRepository.update_state(job.id, JobState.PUBLISHED, published_at=datetime.utcnow())
            else:
                JobRepository.update_state(job.id, JobState.PROCESSING)

            total_latency = int((time.time() - start_time) * 1000)
            JobRepository.update_metrics(
                job.id,
                duration_seconds=actual_duration,
                file_size_bytes=actual_size,
                sha256_hash=sha256,
                download_latency_ms=dl_latency,
                upload_latency_ms=up_latency,
                encode_latency_ms=encode_latency,
                total_latency_ms=total_latency,
            )

            # Tự động cập nhật file Excel lịch sử
            try:
                from tollcal.storage.excel_export import export_jobs_to_excel
                export_jobs_to_excel()
            except Exception:
                pass

            if progress_callback:
                progress_callback("Đồng bộ hoàn tất 100%!", 1.0)

            logger.info(
                f"[bold green]🎉 Đồng bộ thành công video {source_meta.video_id} -> UCircle Wavee ({ucircle_video_id}) trong {total_latency / 1000:.1f}s![/bold green]"
            )
            return JobRepository.get_by_id(job.id) or job

        except Exception as e:
            error_code = getattr(e, "code", "UNEXPECTED_ERROR")
            JobRepository.update_state(
                job.id, JobState.FAILED_PERMANENT, error_code=error_code, error_message=str(e)
            )
            # Cập nhật file Excel cả khi lỗi để tiện theo dõi
            try:
                from tollcal.storage.excel_export import export_jobs_to_excel
                export_jobs_to_excel()
            except Exception:
                pass
            logger.error(f"[red]✖ Đồng bộ video thất bại: {e}[/red]")
            raise
        finally:
            # Luôn dọn dẹp file tạm nếu còn sót lại
            if temp_video_path and temp_video_path.exists():
                temp_manager.delete_file_safe(temp_video_path)
