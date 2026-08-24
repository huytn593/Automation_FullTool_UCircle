#!/usr/bin/env python3
import sys
from pathlib import Path

# Thêm thư mục src vào sys.path để có thể gọi trực tiếp
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from tollcal.cli import app

if __name__ == "__main__":
    app()
