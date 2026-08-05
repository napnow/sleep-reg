@echo off
chcp 65001 >nul
echo Starting ChatGPT Registration Tool (GUI)...
cd /d "%~dp0"

REM Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Install dependencies if needed
if not exist "requirements_installed.flag" (
    echo Installing dependencies...
    pip install -r requirements.txt
    if %errorlevel% equ 0 (
        echo flag > requirements_installed.flag
    )
)

REM Run the GUI
python chatgpt_register_ttk.py gui

pause
