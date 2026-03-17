#!/bin/bash
# GAS Control System - Linux/macOS 실행 스크립트

cd "$(dirname "$0")"

# 가상환경이 있으면 활성화
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# PySide6 설치 확인
python3 -c "import PySide6" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[설치] PySide6 설치 중..."
    pip3 install PySide6
fi

echo "[시작] GAS Control System"
python3 main.py
