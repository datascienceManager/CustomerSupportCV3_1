# 🎙️ AI Voice Agent

A production-ready AI-powered customer support agent that handles **voice and chat queries**, classifies them by department, stores them in **Google Sheets + SQLite/MySQL**, and sends **AI-generated email summaries** to the relevant teams — all built on **Streamlit + Claude AI**, deployable to **Azure Container Apps**.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Streamlit Web App                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Chat Page   │  │  Dashboard   │  │  Admin Panel │  │
│  │ (text+voice) │  │ (analytics)  │  │ (email ctrl) │  │
│  └──────┬───────┘  └──────────────┘  └──────────────┘  │
└─────────┼───────────────────────────────────────────────┘
          │ query
          ▼
┌─────────────────────┐     ┌──────────────────────────┐
│   Claude AI Agent   │────▶│  Category Classifier     │
│  (claude-sonnet-4)  │     │  product / payment /     │
│   + Whisper STT     │     │  unknown                 │
│   + gTTS TTS        │     └──────────────────────────┘
└─────────────────────┘
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
│   Claude Summary Engine   │──▶ SendGrid Email
│  per-department digest    │   📦 Product Team
└───────────────────────────┘   💳 Payments Team
```

---

## ✨ Features

| Feature | Details |
|---------|---------|
| 🎤 Voice Input | Upload WAV/WebM → OpenAI Whisper STT |
| 💬 Chat Input | Real-time text conversation |
| 🤖 AI Responses | Claude Sonnet with conversation history |
| 🏷️ Auto Classification | Product / Payment / Unknown |
| 😊 Sentiment Detection | Positive / Neutral / Negative |
| 🗄️ SQL Storage | SQLite (demo) or MySQL (production) — **free** |
| 📊 Google Sheets | Live append with all query metadata |
| 📧 Email Summaries | AI-generated daily digests via SendGrid |
| ⏰ Scheduler | APScheduler background job (9am UTC default) |
| 📊 Dashboard | Real-time charts, metrics, query table |
| ⚙️ Admin Panel | Manual email triggers, data export, config status |
| 🔊 TTS Playback | gTTS auto-plays AI responses |
| 🐳 Docker | Multi-stage Dockerfile, docker-compose for local dev |
| ☁️ Azure | Bicep IaC, Container Apps, Key Vault, ACR, CI/CD |

---

## 🚀 Quick Start (Local)

### 1. Clone & install

```bash
git clone https://github.com/yourorg/ai-voice-agent.git
cd ai-voice-agent

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set ANTHROPIC_API_KEY
```

### 3. Run

```bash
streamlit run app.py
```

Open http://localhost:8501

---

## 🐳 Docker (Local)

```bash
# Build & run with SQLite
docker compose up --build

# With MySQL (production-like)
docker compose --profile mysql up --build
```

---

## ☁️ Azure Deployment

### Option A — One-shot script

```bash
# Requires: az CLI logged in
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

### Option C — GitHub Actions CI/CD

Set these repository secrets:

| Secret | Value |
|--------|-------|
| `ACR_LOGIN_SERVER` | `youracr.azurecr.io` |
| `ACR_USERNAME` | ACR admin username |
| `ACR_PASSWORD` | ACR admin password |
| `AZURE_CREDENTIALS` | `az ad sp create-for-rbac` output |
| `PRODUCT_DEPT_EMAIL` | product@yourcompany.com |
| `PAYMENT_DEPT_EMAIL` | payments@yourcompany.com |

Every push to `main` triggers: Test → Build → Push to ACR → Deploy to Container Apps.

---

## 🔧 Configuration

All config lives in `.env` (see `.env.example`). Key settings:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Voice (optional — enables Whisper STT)
OPENAI_API_KEY=sk-...

# Email summaries (optional — logs to console if not set)
SENDGRID_API_KEY=SG....
PRODUCT_DEPT_EMAIL=product@yourcompany.com
PAYMENT_DEPT_EMAIL=payments@yourcompany.com

# Google Sheets (optional)
GOOGLE_SHEET_ID=your_sheet_id
GOOGLE_SERVICE_ACCOUNT_JSON=./config/google_service_account.json

# Database
DB_TYPE=sqlite                          # or mysql
SQLITE_DB_PATH=./data/queries.db
```

See [Google Sheets Setup Guide](docs/google_sheets_setup.md) for sheet config.

---

## 🧪 Tests

```bash
pytest tests/ -v --tb=short
```

---

## 📁 Project Structure

```
ai-voice-agent/
├── app.py                          # Streamlit entry point + routing
├── requirements.txt
├── Dockerfile                      # Multi-stage production image
├── docker-compose.yml
├── .env.example
│
├── config/
│   ├── settings.py                 # Centralised config (dataclasses + .env)
│   └── google_service_account.json # (you add this — not in git)
│
├── services/
│   ├── ai_agent.py                 # Claude AI — query answering + summarisation
│   ├── database.py                 # SQLAlchemy models + CRUD
│   ├── google_sheets.py            # gspread integration
│   └── email_service.py           # SendGrid + department routing
│
├── utils/
│   ├── voice_utils.py              # Whisper STT + gTTS TTS
│   └── scheduler.py               # APScheduler background jobs
│
├── pages/
│   ├── chat_page.py               # Chat + voice UI
│   ├── dashboard_page.py          # Analytics charts
│   └── admin_page.py              # Admin controls
│
├── azure/
│   ├── main.bicep                 # Azure IaC (Container Apps + ACR + KV)
│   ├── parameters.json
│   └── deploy.sh                  # One-shot deploy script
│
├── .github/
│   └── workflows/
│       └── deploy-azure.yml       # CI/CD pipeline
│
├── docs/
│   └── google_sheets_setup.md
│
└── tests/
    └── test_services.py
```

---

## 🗺️ Roadmap (Post-POC)

- [ ] Add more departments (HR, Technical Support, Sales)
- [ ] Live browser microphone recording (streamlit-webrtc)
- [ ] Multi-language support (gTTS + Whisper multilingual)
- [ ] Azure MySQL Flexible Server for persistent production DB
- [ ] Power BI / Grafana dashboard integration
- [ ] Slack / Teams notification integration
- [ ] Customer authentication + query history
- [ ] Fine-tuned classification model

---

## 📜 License

MIT — see LICENSE file.
