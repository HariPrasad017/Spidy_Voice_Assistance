# S.P.I.D.Y v6.1 — Disaster Recovery & Clean Environment Setup Guide

This document records the exact steps to recreate the S.P.I.D.Y runtime environment from scratch on a clean machine.

---

## 1. Prerequisites & System Dependencies

### Operating System
- **Windows 10/11 (64-bit)** recommended for native OS commands, GDI/PowerShell screenshot capture, and audio endpoints.
- Linux / macOS supported with simulated application launches and local desktop path fallbacks.

### Core Software
1. **Python 3.10+**: Ensure Python is added to system `PATH`.
2. **FFmpeg**:
   - Download an essentials build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) or install via `winget install Gyan.FFmpeg` or `choco install ffmpeg`.
   - Verify `ffmpeg.exe` is in `PATH` or place in `E:\ffmpeg-9.0.2-essentials_build\bin` (auto-detected by `config.py`).
3. **NVIDIA CUDA Toolkit (Optional but recommended for GPU)**:
   - Compatible NVIDIA driver for PyTorch CUDA acceleration (tested on RTX 3050 Laptop GPU).

---

## 2. Environment Setup

### Step 1: Clone / Unpack Repository
Extract the backup archive to your desired directory:
```powershell
cd E:\Spidy_Voice_Assistance-main
```

### Step 2: Create Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
pip install openai-whisper
```

*(Note: PyTorch with CUDA can be installed via `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121` if GPU acceleration is desired).*

### Step 4: Environment Variables (`.env`)
Copy the template file to `.env`:
```powershell
copy .env.example .env
```
Edit `.env` and set your credentials:
```ini
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-20b
WHISPER_MODEL_SIZE=base
WHISPER_LANGUAGE=auto
SPIDY_DEBUG=false
PORT=5000
```

---

## 3. Database & State Initialization
The SQLite conversation memory database (`spidy_memory.db`) will automatically initialize its schema (`conversations`, `messages`, `memory` tables) upon first run. No manual migration is needed.

---

## 4. Run Automated Validation Suite
Execute the comprehensive test suite to confirm complete readiness:
```powershell
python -m unittest test_spidy.py
```
Expected output:
```
Ran 92 tests in ~25s
OK
```

---

## 5. Launch the Application
Start the Flask web server:
```powershell
python app.py
```
Access the dashboard at:
```
http://localhost:5000
```
