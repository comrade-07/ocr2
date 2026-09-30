@echo off
setlocal

cd /d "%~dp0"
title Scope 2 OCR Manual Review App

if not exist ".venv\Scripts\python.exe" (
    echo Python was not found in .venv.
    echo Run this first:
    echo .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting Scope 2 OCR Manual Review App...
echo.
echo A browser window should open at:
echo http://localhost:8501
echo.
echo Keep this window open while using the app.
echo Press Ctrl+C here when you want to stop the app.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 5; Start-Process 'http://localhost:8501'"
".venv\Scripts\python.exe" -m streamlit run "review_app.py" --server.port 8501 --server.headless true

echo.
echo The app stopped or failed to start.
pause

endlocal
