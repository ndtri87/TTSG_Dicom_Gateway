#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python" ]; then
    echo "[LOI] Chua cai dat. Hay chay ./setup.sh truoc."
    exit 1
fi

echo "Dang khoi dong DICOM Gateway Service..."
echo "Nhan Ctrl+C de dung."
./.venv/bin/python main.py
