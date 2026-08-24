from typing import Optional
from tollcal.domain.models import SyncJob
from tollcal.domain.states import JobState
from tollcal.storage.repositories import JobRepository


def is_already_synced(
    provider: str,
    source_video_id: str,
    target_account_id: str,
    circle_id: Optional[str] = None,
) -> bool:
    """Kiểm tra video đã được đồng bộ thành công hoặc đang trong tiến trình trên cùng 1 Circle hay chưa."""
    job = JobRepository.get_by_source_id(provider, source_video_id, target_account_id, circle_id)
    if not job:
        return False

    # Nếu đã từng được publish, encode hoặc đang review thì coi như đã sync
    if job.state in (
        JobState.PUBLISHED,
        JobState.ENCODED,
        JobState.UNDER_REVIEW,
        JobState.PROCESSING,
        JobState.DUPLICATE,
    ):
        return True

    return False
