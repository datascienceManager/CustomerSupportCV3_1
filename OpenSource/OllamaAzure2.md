
## What Changed (Anthropic → Ollama)

### `services/ai_agent.py` — core rewrite
- Replaced `anthropic` SDK with direct `requests` calls to Ollama's `/api/chat` REST API
- Added `check_ollama_health()` — pings `/api/tags`, returns `{online, models, error}`
- Added `list_available_models()` — lists installed models from Ollama
- Added `_parse_json_response()` — robust parser that handles markdown fences, embedded JSON, and leading prose (LLMs are noisier than Claude at following JSON-only instructions)
- Added graceful fallback: if JSON parse fails, the raw text is returned as the answer rather than crashing
- `generate_department_summary()` now includes a built-in fallback summary if Ollama is unreachable

### `config/settings.py`
- Removed `anthropic_api_key` field
- Added `OllamaConfig` dataclass with `base_url`, `model`, `timeout`, `username`, `password`
- `AppConfig` gains `ollama: OllamaConfig` field

### `pages/admin_page.py` — new "LLM & Config" tab
- Live Ollama health card (green/red) showing server URL and active model
- Lists all installed models with the active one highlighted
- In-session **model switcher** — select any installed model and apply it without restarting
- Setup instructions shown when Ollama is offline

### `docker-compose.yml`
- Added `ollama` service using `ollama/ollama:latest` with a persistent `ollama_models` volume
- Added `ollama-pull` one-shot service that auto-pulls `$OLLAMA_MODEL` on first run
- App service sets `OLLAMA_BASE_URL=http://ollama:11434` pointing to the sidecar

### `azure/main.bicep`
- Removed `anthropicApiKey` parameter entirely
- Added Ollama as a **sidecar container** (shares `localhost` with the Streamlit container)
- Ollama gets 1 CPU / 4Gi RAM; Streamlit gets 0.5 CPU / 1Gi RAM
- `OLLAMA_BASE_URL=http://localhost:11434` — no network hop needed

### `tests/test_services.py`
- All Ollama calls mocked with `unittest.mock.patch` — tests run fully offline
- 12 new Ollama-specific tests covering: success, payment category, markdown fences, invalid category normalisation, connection errors, JSON fallback, health check, summary fallback, and `_parse_json_response` edge cases

### `requirements.txt` — `anthropic` removed, `ollama==0.2.1` + `requests` added
### `.env.example` — full model menu with size/RAM guide, Anthropic key removed
### `Dockerfile` — removed `pyaudio` (no longer needed), kept `ffmpeg` for audio
### `README.md` — Ollama quick-start, model comparison table, Docker/Azure sections updated
