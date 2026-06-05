#!/usr/bin/env bash
# ubisam-mail-mcp 원클릭 설치 + setup wizard (Ubuntu/WSL CLI용)
#
# 사용법 (레포를 clone 한 뒤 레포 안에서):
#   bash scripts/setup.sh
#
# 하는 일: Python 3.10+ 자동 탐색 -> .venv 생성 -> pip install -e . -> setup wizard(--web-setup) 실행
set -euo pipefail

# 레포 루트(이 스크립트의 상위 폴더)로 이동
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
echo "[ubisam-mail-mcp] 작업 폴더: $REPO_ROOT"

# 1) Python 3.10+ 탐색
find_python() {
  for c in python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)' 2>/dev/null; then
        echo "$c"; return 0
      fi
    fi
  done
  return 1
}

if ! PY="$(find_python)"; then
  echo "Python 3.10 이상을 찾지 못했습니다. 설치 후 다시 실행하세요:" >&2
  echo "  sudo apt update && sudo apt install -y python3 python3-venv python3-pip" >&2
  exit 1
fi
echo "[1/4] 사용할 Python: $PY ($($PY --version 2>&1))"

# 2) .venv 생성 (이미 있으면 재사용)
if [ -x ".venv/bin/python" ]; then
  echo "[2/4] 기존 .venv 재사용 (새로 만들려면 'rm -rf .venv' 후 재실행)"
else
  echo "[2/4] .venv 생성 중..."
  if ! "$PY" -m venv .venv; then
    echo "venv 생성 실패. python3-venv가 필요할 수 있습니다:" >&2
    echo "  sudo apt install -y python3-venv" >&2
    exit 1
  fi
fi

# venv에 pip이 없으면(ensurepip 누락) 안내
if ! ./.venv/bin/python -m pip --version >/dev/null 2>&1; then
  echo "venv에 pip이 없습니다. python3-venv 설치 후 .venv를 다시 만드세요:" >&2
  echo "  sudo apt install -y python3-venv && rm -rf .venv && bash scripts/setup.sh" >&2
  exit 1
fi

# 3) 편집 설치
echo "[3/4] 패키지 설치 중 (pip install -e .)..."
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e .

# 4) setup wizard 실행 (브라우저 기반 웹 setup)
echo "[4/4] setup wizard 실행 (--web-setup). 브라우저가 안 열리면 터미널의 http://127.0.0.1:8765/ 주소를 직접 여세요."
./.venv/bin/python -m ubisam_mail_mcp.setup_wizard --web-setup
