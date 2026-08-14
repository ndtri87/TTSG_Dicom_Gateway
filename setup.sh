#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=== Cai dat DICOM Gateway Service ==="

if ! command -v python3 &> /dev/null; then
    echo "[LOI] Khong tim thay python3. Hay cai Python 3.10+."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Dang tao moi truong ao..."
    python3 -m venv .venv
fi

echo "Dang cai thu vien..."
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt

echo ""
echo "=== Cai dat xong ==="
echo "Buoc tiep theo:"
echo "  1. Mo config.yaml, sua IP/Port/AE Title cua PACS that."
echo "  2. Chay ./test_ket_noi_pacs.sh de kiem tra ket noi PACS."
echo "  3. Chay ./run.sh de khoi dong service."
