@echo off
title Planetary Simulation Launcher

echo Setting Database URL...
set DATABASE_URL=postgresql://postgres:PigPig3897!!@localhost:5432/worldsim

echo Disabling PyTorch/Sentence-Transformers (using fast deterministic hash-based embeddings fallback)...
set FORCE_EMBEDDING_FALLBACK=1

echo Disabling Kivy command line argument parsing...
set KIVY_NO_ARGS=1

echo Starting Backend FastAPI Server in a separate window...
start "WorldSim FastAPI Hub" cmd /k "set FORCE_EMBEDDING_FALLBACK=1&&set DATABASE_URL=postgresql://postgres:PigPig3897!!@localhost:5432/worldsim&&python -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo Waiting for server to initialize (3 seconds)...
timeout /t 3 /nobreak

echo Automatically ingesting Obsidian Vault lore...
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/narrative/ingest-vault', data=b'')"

echo ==========================================
echo Which client would you like to launch?
echo [1] Planetary Builder Dashboard (Admin Editor)
echo [2] Character Simulation Viewport (Normal Client)
echo ==========================================
set /p opt="Enter choice (1 or 2): "

if "%opt%"=="2" (
    echo Starting Character Simulation Viewport...
    python quad_nested_client.py
) else (
    echo Starting Planetary Builder Dashboard...
    python main_client.py --admin-editor
)

pause
