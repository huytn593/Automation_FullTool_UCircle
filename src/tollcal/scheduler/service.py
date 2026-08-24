import time
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from tollcal.config import settings
from tollcal.domain.models import ChannelMonitor
from tollcal.domain.states import RightsBasis
from tollcal.observability.logging import logger
from tollcal.storage.repositories import ChannelRepository
from tollcal.sync.orchestrator import SyncOrchestrator


class ChannelSyncDaemon:
    """Daemon chạy ngầm định kỳ quét danh sách kênh Creator và đồng bộ video mới."""

    def __init__(self, orchestrator: Optional[SyncOrchestrator] = None):
        self.orchestrator = orchestrator or SyncOrchestrator()
        self.interval_minutes = settings.auto_sync_interval_minutes

    def scan_monitored_channels_once(self) -> None:
        """Quét 1 vòng tất cả các kênh đang active."""
        channels = ChannelRepository.list_active_channels()
        if not channels:
            logger.info("[Daemon] Chưa có kênh nào trong danh sách theo dõi.")
            return

        logger.info(f"[Daemon] Bắt đầu quét {len(channels)} kênh đang theo dõi...")

        for ch in channels:
            try:
                logger.info(f"[Daemon] Đang quét kênh: [bold]{ch.channel_url}[/bold]")
                # Lấy 3 video mới nhất
                videos = self.orchestrator.tiktok.list_channel_videos(ch.channel_url, limit=3)
                if not videos:
                    logger.debug(f"[Daemon] Kênh {ch.channel_url} không có video mới.")
                    continue

                new_video_synced = 0
                for v in reversed(videos):  # Đồng bộ video cũ trước, mới sau để giữ đúng thứ tự
                    try:
                        self.orchestrator.sync_single_video(
                            source_url_or_path=v.source_url,
                            rights_basis=ch.rights_basis,
                            poll_encode=True,
                        )
                        new_video_synced += 1
                        time.sleep(5)  # Nghỉ 5s giữa các lần tải để tránh rate limit
                    except Exception as e:
                        logger.warning(f"[Daemon] Bỏ qua video {v.video_id}: {e}")

                latest_id = videos[0].video_id if videos else None
                ChannelRepository.update_scan_status(ch.id, latest_id)
                logger.info(f"[Daemon] Hoàn tất quét kênh {ch.channel_url} (đã đồng bộ {new_video_synced} video).")

            except Exception as e:
                logger.error(f"[Daemon] Lỗi khi xử lý kênh {ch.channel_url}: {e}")

    def start_blocking(self) -> None:
        """Chạy daemon ở chế độ chặn tiến trình (Blocking Scheduler) cho VPS / Terminal."""
        logger.info(
            f"[bold green]🚀 Khởi động Tollcal Daemon. Chu kỳ quét: {self.interval_minutes} phút/lần.[/bold green]"
        )
        # Quét ngay 1 lần khi khởi động
        self.scan_monitored_channels_once()

        scheduler = BlockingScheduler()
        scheduler.add_job(
            self.scan_monitored_channels_once,
            "interval",
            minutes=self.interval_minutes,
            id="channel_sync_job",
        )
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("[Daemon] Đã nhận tín hiệu dừng daemon.")
