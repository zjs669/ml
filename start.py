"""本地开发启动脚本。

用法：
    python start.py            # 同时启动后端和前端
    python start.py backend    # 只启后端
    python start.py frontend   # 只启前端
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def backend() -> None:
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
        cwd=BACKEND,
    )


def frontend() -> None:
    subprocess.run(["npm", "run", "dev"], cwd=FRONTEND, shell=True)


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target == "backend":
        backend()
    elif target == "frontend":
        frontend()
    else:
        # 同时起两个：前端用子进程，后端占当前终端（Ctrl+C 一起停）
        fe = subprocess.Popen(["npm", "run", "dev"], cwd=FRONTEND, shell=True)
        try:
            backend()
        finally:
            fe.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
