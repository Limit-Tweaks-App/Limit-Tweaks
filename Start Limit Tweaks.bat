@echo off
title Limit Tweaks
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from python.org, then run this file again.
  pause
  exit /b
)

set "OLL=ollama"
where ollama >nul 2>nul
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    set "OLL=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
  ) else (
    echo Installing the free AI engine. This can take a few minutes, please wait.
    winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
    set "OLL=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
  )
)

"%OLL%" list >nul 2>nul
if errorlevel 1 (
  echo Starting the AI engine.
  start "" /b "%OLL%" serve
  timeout /t 6 >nul
)

"%OLL%" list 2>nul | findstr /i "llama3.2" >nul
if errorlevel 1 (
  echo Downloading the AI. This happens once and can take a while.
  "%OLL%" pull llama3.2:3b
  if errorlevel 1 (
    echo.
    echo The AI could not be set up. The app will still open without the chat.
    echo To fix it later, install Ollama from ollama.com/download and run this file again.
    pause
  )
)

start "" pythonw app.py
