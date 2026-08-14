#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python" ]; then
    echo "[LOI] Chua cai dat. Hay chay ./setup.sh truoc."
    exit 1
fi

./.venv/bin/python test_pacs_connection.py
