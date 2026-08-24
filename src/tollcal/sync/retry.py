import time
import functools
from typing import Callable, Any, Tuple, Type
from tollcal.domain.errors import TollcalError
from tollcal.observability.logging import logger


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator thực hiện retry với exponential backoff cho các tác vụ mạng."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    # Nếu là TollcalError và được đánh dấu là không thể retry thì dừng ngay
                    if isinstance(e, TollcalError) and not e.is_retryable:
                        logger.error(f"Lỗi cố định (không thể retry): {e}")
                        raise

                    if attempt == max_retries:
                        logger.error(f"Đã thử lại {max_retries} lần nhưng vẫn thất bại: {e}")
                        raise

                    logger.warning(
                        f"Lỗi ở lần thử {attempt}/{max_retries}: {e}. Đang chờ {delay:.1f}s trước khi thử lại..."
                    )
                    time.sleep(delay)
                    delay *= backoff_factor

            if last_exception:
                raise last_exception

        return wrapper

    return decorator
