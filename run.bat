@echo off
REM GAS Control System - Windows 실행 스크립트
REM Python 3.10 이상 필요

cd /d "%~dp0"

REM 가상환경이 있으면 활성화
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM PySide6 설치 확인
python -c "import PySide6" 2>nul
if errorlevel 1 (
    echo [설치] PySide6 설치 중...
    pip install PySide6
)

echo [시작] GAS Control System
python main.py
pause
