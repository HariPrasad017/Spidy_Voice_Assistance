# 🕷️ S.P.I.D.Y — Spider-Man Personal Intelligence Digital Yield-system

<div align="center">

![Python](https://img.shields.io/badge/Python-3.14-blue?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.1-black?style=for-the-badge&logo=flask)
![PyTorch](https://img.shields.io/badge/PyTorch-2.0-red?style=for-the-badge&logo=pytorch)
![HuggingFace](https://img.shields.io/badge/HuggingFace-Transformers-yellow?style=for-the-badge)
![Groq](https://img.shields.io/badge/Groq-LLaMA3-green?style=for-the-badge)

**An AI-powered voice assistant inspired by JARVIS, built with Spider-Man theme.**
*"With great power comes great responsibility — and great AI!"* 🕷️

[Demo](#demo) • [Features](#features) • [Tech Stack](#tech-stack) • [Installation](#installation) • [Usage](#usage)

</div>

---

## 🎯 Overview

S.P.I.D.Y is a full-stack AI voice assistant that combines multiple AI/ML technologies into a single, production-ready application. Built as a portfolio project targeting AI/ML engineering roles, it demonstrates practical implementation of:

- **Large Language Models** (Groq + LLaMA 3.1)
- **Transformer-based NLP** (HuggingFace zero-shot classification)
- **PyTorch deep learning** (DistilBERT sentiment analysis)
- **Automatic Speech Recognition** (OpenAI Whisper — GPU-ready)
- **RESTful API design** (Flask backend)
- **Real-time voice I/O** (Web Speech API)

---

## ✨ Features

### 🧠 AI & NLP
| Feature | Technology |
|---|---|
| Conversational AI | Groq API + LLaMA 3.1 8B |
| Intent Detection | HuggingFace `facebook/bart-large-mnli` (zero-shot) |
| Sentiment Analysis | PyTorch + DistilBERT (`distilbert-base-uncased-finetuned-sst-2-english`) |
| Speech Recognition | Web Speech API + OpenAI Whisper (GPU-ready) |
| Text-to-Speech | Browser SpeechSynthesis API |

### 🖥️ System Commands
- Open/close applications (Chrome, VS Code, Notepad, Edge, etc.)
- Volume & brightness control
- Screenshot capture
- File & folder operations
- System shutdown/restart/lock
- Reminders & alarms
- Notes management

### 🌐 Web Features
- Real-time weather (wttr.in API)
- News search (Google News)
- YouTube & Google search
- Stock price lookup
- Website launcher

### 🎨 UI/UX
- Spider-Man themed dark interface
- Animated boot sequence
- Real-time waveform visualization
- Rotating orb with state indicators
- Mobile responsive design
- Code syntax highlighting with copy button

---

## 🛠️ Tech Stack

```
Backend:
├── Python 3.14
├── Flask 3.1 (REST API)
├── Groq API (LLaMA 3.1 8B Instant)
├── HuggingFace Transformers
│   ├── facebook/bart-large-mnli (Intent Detection)
│   └── distilbert-base-uncased-finetuned-sst-2-english (Sentiment)
├── PyTorch (Deep Learning Inference)
├── OpenAI Whisper (ASR — GPU-ready)
└── pydub + ffmpeg (Audio Processing)

Frontend:
├── HTML5 + CSS3 + Vanilla JavaScript
├── Web Speech API (Voice I/O)
├── Canvas API (Waveform + Web animation)
└── Fetch API (REST communication)
```

---

## 🏗️ Architecture

```
User Voice Input
      │
      ▼
Web Speech API / Whisper ASR
      │
      ▼
Flask REST API (/api/chat)
      │
      ├── Step 1: Keyword Command Parser (fast)
      │
      ├── Step 2: HuggingFace Intent Detector
      │           (zero-shot classification)
      │
      ├── Step 3: PyTorch Sentiment Analyzer
      │           (tone-aware responses)
      │
      └── Step 4: Groq LLaMA 3.1 (general AI)
                  (emotion-adjusted prompting)
                        │
                        ▼
              S.P.I.D.Y Response
                        │
                        ▼
              Text-to-Speech Output
```

---

## 📦 Installation

### Prerequisites
- Python 3.10+
- Git
- Chrome browser (for voice features)

### Setup

```bash
# Clone the repository
git clone https://github.com/HariPrasad017/Spidy_Voice_Assistance.git
cd Spidy_Voice_Assistance

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add your API keys
```

### Environment Variables

Create a `.env` file:
```env
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here  # optional
```

Get free API keys:
- **Groq**: https://console.groq.com (Free, fast)
- **Gemini**: https://aistudio.google.com (Free tier)

### Run

```bash
python app.py
```

Open `http://127.0.0.1:5000` in Chrome!

---

## 🎮 Usage

### Voice Commands

| Command | Action |
|---|---|
| "Open Chrome" | Launches Chrome browser |
| "Take screenshot" | Saves screenshot to Desktop |
| "Set volume to 50" | Sets system volume to 50% |
| "Increase brightness to 80" | Sets brightness to 80% |
| "Note buy groceries" | Saves a note |
| "Remind me in 30 minutes" | Sets a reminder |
| "Weather in Chennai" | Gets live weather |
| "Who is Iron Man?" | AI answers with Spidey personality |
| "Give Python code for sorting" | Returns formatted code |
| "Play Linkin Park" | Opens YouTube search |
| "Shutdown computer" | Initiates shutdown (30 sec delay) |

### API Endpoints

```
GET  /api/status          - System status + AI model info
POST /api/chat            - Main chat endpoint
POST /api/sentiment       - PyTorch sentiment analysis
POST /api/sentiment/batch - Batch sentiment analysis
GET  /api/weather         - Live weather data
GET  /api/news            - Latest news
GET  /api/notes           - Saved notes
GET  /api/reminders       - Active reminders
POST /api/whisper/transcribe - Whisper ASR transcription
```

---

## 🧪 AI Models Used

| Model | Task | Parameters |
|---|---|---|
| `llama-3.1-8b-instant` | Conversational AI | 8B |
| `facebook/bart-large-mnli` | Zero-shot intent classification | 400M |
| `distilbert-base-uncased-finetuned-sst-2-english` | Sentiment analysis | 66M |
| `openai/whisper-base` | Speech recognition | 74M |

---

## 📁 Project Structure

```
Spidy_Voice_Assistance/
├── app.py                  # Flask backend + all API routes
├── intent_detector.py      # HuggingFace zero-shot classifier
├── sentiment_analyzer.py   # PyTorch DistilBERT sentiment model
├── whisper_asr.py          # OpenAI Whisper ASR module
├── requirements.txt        # Python dependencies
├── .env                    # API keys (not in repo)
├── .gitignore
└── static/
    ├── SPIDY.html          # Main UI (Spider-Man themed)
    ├── style.css           # CSS styling
    └── app.js              # Frontend JavaScript
```

---

## 🚀 Roadmap

- [x] Phase 1: Spider-Man UI + Boot sequence
- [x] Phase 2: Voice I/O + Wake word
- [x] Phase 3: Groq AI Brain
- [x] Phase 4: System commands
- [x] Phase 5: HuggingFace + PyTorch + Whisper ASR
- [ ] Phase 6: Deploy on Linux server with NGINX
- [ ] Phase 7: Tamil NLP model integration
- [ ] Phase 8: Multi-user support

---

## 👨‍💻 Developer

**Hari Prasad**
- GitHub: [@HariPrasad017](https://github.com/HariPrasad017)
- Built for: AI/ML Engineering Portfolio

---

## 📄 License

MIT License — feel free to use and modify!

---

<div align="center">
Made with ❤️ and 🕷️ by Hari Prasad
<br>
<i>"Anyone can wear the mask." — Miles Morales</i>
</div>