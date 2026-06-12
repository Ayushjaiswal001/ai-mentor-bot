@echo off
title AI Mentor Bot
cd /d D:\ai-mentor-bot
echo Starting AI Mentor Bot... (close this window or press Ctrl+C to stop)
.venv\Scripts\python.exe -m app.main
echo.
echo Bot stopped. If this was unexpected, read the error above.
pause
