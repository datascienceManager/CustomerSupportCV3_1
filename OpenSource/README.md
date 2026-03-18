# 🎙️ AI Voice Agent (Ollama Edition)

A production-ready AI-powered customer support agent built on **Ollama** (local open-source LLM). Handles voice and chat queries, classifies them by department, stores them in **Google Sheets + SQLite/MySQL**, and sends **AI-generated email summaries** — all deployed as a **Streamlit** app on **Azure Container Apps**.

> 💡 **No API keys required for the AI** — Ollama runs entirely on your own machine or server.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Streamlit Web App                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Chat Page   │  │  Dashboard   │  │  Admin Panel │  │
│  │ (text+voice) │  │ (analytics)  │  │ (Ollama ctrl)│  │
│  └──────┬───────┘  └──────────────┘  └──────────────┘  │
└─────────┼───────────────────────────────────────────────┘
          │ query
          ▼
┌──────────────────────┐     ┌──────────────────────────┐
│  Ollama LLM Server   │────▶│  JSON Output Parser      │
│  (llama3.2 / mistral │     │  category / sentiment /  │
│   gemma2 / phi3 ...) │     │  answer / escalate       │
│  + Whisper STT (opt) │     └──────────────────────────┘
│  + gTTS TTS          │
└──────────────────────┘
          │ save
     ┌────┴────┐
     ▼         ▼
┌─────────┐  ┌──────────────┐
│  SQLite │  │ Google Sheet │
│ /MySQL  │  │  (live log)  │
└────┬────┘  └──────────────┘
     │ daily @ 9am UTC (APScheduler)
     ▼
┌───────────────────────────┐
│  Ollama Summary Engine    │──▶ SendGrid Email
│  per-department digest    │   📦 Product Team
└───────────────────────────┘   💳 Payments Team
```

---

## ✨ Features

| Feature | Details |
|---------|---------|
| 🤖 Local LLM | Ollama — runs 100% offline, no API key needed |
| 🔀 Model Switcher | Switch models live from Admin panel |
| 🎤 Voice Input | Upload WAV/WebM → OpenAI Whisper STT (optional) |
| 💬 Chat Input | Real-time text conversation with history |
| 🏷️ Auto Classification | Product / Payment / Unknown (via LLM JSON output) |
| 😊 Sentiment Detection | Positive / Neutral / Negative |
| 🗄️ SQL Storage | SQLite (demo) or MySQL (production) — **free** |
| 📊 Google Sheets | Live append with all query metadata |
| 📧 Email Summaries | Ollama-generated daily digests via SendGrid |
| ⏰ Scheduler | APScheduler background job (9am UTC default) |
| 📊 Dashboard | Real-time charts, metrics, query table |
| ⚙️ Admin Panel | Ollama health + model list, email triggers, data export |
| 🔊 TTS Playback | gTTS auto-plays AI responses |
| 🐳 Docker | Compose with Ollama sidecar container |
| ☁️ Azure | Bicep IaC, Container Apps with Ollama sidecar, Key Vault |

---

## 🚀 Quick Start (Local)

### 1. Install & start Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows: download from https://ollama.com/download

# Start the server
ollama serve

# Pull a model (pick one)
ollama pull llama3.2       # 3B  — fastest, great for demos
ollama pull mistral        # 7B  — excellent quality/speed balance
ollama pull gemma2         # 9B  — Google, very capable
ollama pull phi3           # 3.8B — lightweight Microsoft model
```

### 2. Clone & install Python deps

```bash
git clone https://github.com/yourorg/ai-voice-agent.git
cd ai-voice-agent

python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Minimum required — everything else is optional:
# OLLAMA_BASE_URL=http://localhost:11434   (default)
# OLLAMA_MODEL=llama3.2                   (default)
```

### 4. Run

```bash
streamlit run app.py
```

Open http://localhost:8501 — start chatting immediately, no API keys needed!

---

## 🐳 Docker (Local — with Ollama sidecar)

```bash
# Pulls Ollama image + your app, downloads the model automatically
docker compose up --build

# With MySQL (production-like)
docker compose --profile mysql up --build
```

> First run will download the Ollama model (~2GB for llama3.2). Subsequent starts use the cached volume.

---

## 🤖 Recommended Models

| Model | Size | Best For |
|-------|------|----------|
| `llama3.2` | 3B | Fast demos, low RAM (needs ~4GB) |
| `llama3.1` | 8B | Best quality/speed balance (~8GB) |
| `mistral` | 7B | Excellent instruction following (~5GB) |
| `gemma2` | 9B | Strong reasoning (~7GB) |
| `phi3` | 3.8B | Lightweight, great for small machines |
| `qwen2.5` | 7B | Strong multilingual support |
| `deepseek-r1` | 7B | Strong reasoning tasks |
| `llama3.1:70b` | 70B | Highest quality (needs GPU + ~48GB RAM) |

Switch models in the **Admin Panel → LLM & Config** tab at runtime.

---

## ☁️ Azure Deployment

### Option A — One-shot script

```bash
bash azure/deploy.sh
```

### Option B — Manual Bicep

```bash
az group create --name ai-voice-agent-rg --location eastus

az deployment group create \
  --resource-group ai-voice-agent-rg \
  --template-file azure/main.bicep \
  --parameters @azure/parameters.json
```

The Bicep template deploys Ollama as a **sidecar container** alongside the Streamlit app in the same Container App revision — they share `localhost`, so no network hop.

> ⚠️ **Azure Container Apps free tier** does not include GPU. Use CPU-optimised models like `llama3.2` (3B) or `phi3` for cloud deployment. For GPU, use Azure VM or AKS with NVIDIA node pools.

### Option C — GitHub Actions CI/CD

Set these repository secrets:

| Secret | Value |
|--------|-------|
| `ACR_LOGIN_SERVER` | `youracr.azurecr.io` |
| `ACR_USERNAME` | ACR admin username |
| `ACR_PASSWORD` | ACR admin password |
| `AZURE_CREDENTIALS` | `az ad sp create-for-rbac` JSON output |
| `PRODUCT_DEPT_EMAIL` | product@yourcompany.com |
| `PAYMENT_DEPT_EMAIL` | payments@yourcompany.com |

Every push to `main` triggers: Test → Build → Push to ACR → Deploy.

---

## 🔧 Configuration

```bash
# Ollama (required)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OLLAMA_TIMEOUT=120

# Voice STT — optional (without this, voice still works via file upload)
OPENAI_API_KEY=sk-...

# Email summaries — optional (logs to console if not set)
SENDGRID_API_KEY=SG....
PRODUCT_DEPT_EMAIL=product@yourcompany.com
PAYMENT_DEPT_EMAIL=payments@yourcompany.com

# Google Sheets — optional
GOOGLE_SHEET_ID=your_sheet_id
GOOGLE_SERVICE_ACCOUNT_JSON=./config/google_service_account.json

# Database
DB_TYPE=sqlite          # or mysql
SQLITE_DB_PATH=./data/queries.db
```

---

## 🧪 Tests

```bash
pytest tests/ -v --tb=short
```

All Ollama calls are mocked — tests run fully offline with no model required.

---

## 📁 Project Structure

```
ai-voice-agent/
├── app.py                          # Streamlit entry point
├── requirements.txt
├── Dockerfile
├── docker-compose.yml             # Includes Ollama sidecar
├── .env.example
│
├── config/
│   └── settings.py               # OllamaConfig + all other settings
│
├── services/
│   ├── ai_agent.py               # Ollama REST client, JSON parser, summaries
│   ├── database.py               # SQLAlchemy models + CRUD
│   ├── google_sheets.py          # gspread integration
│   └── email_service.py          # SendGrid + department routing
│
├── utils/
│   ├── voice_utils.py            # Whisper STT + gTTS TTS
│   └── scheduler.py              # APScheduler background jobs
│
├── pages/
│   ├── chat_page.py              # Chat + voice UI
│   ├── dashboard_page.py         # Analytics charts
│   └── admin_page.py            # Ollama status + model switcher + admin
│
├── azure/
│   ├── main.bicep                # Streamlit + Ollama sidecar on Container Apps
│   ├── parameters.json
│   └── deploy.sh
│
├── .github/workflows/
│   └── deploy-azure.yml
│
└── tests/
    └── test_services.py          # Fully mocked Ollama tests
```

---

## 🗺️ Roadmap

- [ ] Live browser microphone (streamlit-webrtc)
- [ ] GPU support on Azure AKS
- [ ] More departments (HR, Technical, Sales)
- [ ] Persistent Ollama model storage via Azure File Share
- [ ] Slack / Teams notifications
- [ ] Fine-tuned classification model with Ollama custom Modelfile
