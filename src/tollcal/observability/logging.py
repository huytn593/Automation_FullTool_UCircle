import logging
import sys
from rich.logging import RichHandler
from rich.console import Console

console = Console()


def setup_logger(name: str = "tollcal", level: str = "INFO") -> logging.Logger:
    """Khởi tạo logger với giao diện Rich thân thiện."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            markup=True,
            show_time=True,
            show_path=False,
        )
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()
