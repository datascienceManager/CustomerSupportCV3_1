Let me give you a thorough visual explanation of the entire flow.Let me build this as a comprehensive interactive visual guide.Here's the full conceptual breakdown to go with the interactive guide above.

---

**The core concept to understand:** Ollama is just a REST server. Your Streamlit app calls `http://localhost:11434/api/chat` — the same way it would call any API. The entire deployment challenge is simply *getting Ollama running alongside your app*.

---

**Locally (Docker Compose)** — three containers, one network:

- `ollama` — the long-running LLM server with a named volume (`ollama_models`) so downloaded weights survive container restarts
- `ollama-pull` — a one-shot helper that sleeps 5 seconds then runs `ollama pull llama3.2` inside the Ollama container, then exits
- `app` — your Streamlit app, with `OLLAMA_BASE_URL=http://ollama:11434` pointing at the sidecar by its Docker Compose service name

---

**In Azure (Container Apps)** — the "sidecar pattern":

Both your Streamlit app and Ollama run as containers **inside the same Container App revision**. Because they share a network namespace, the app reaches Ollama at `http://localhost:11434` — not a public URL, not a separate service, just localhost. This means:

- Zero latency between app and model
- Ollama is never exposed to the internet
- No separate Azure service needed for Ollama
- They scale together as a unit

The only image you push to ACR is your **Streamlit app**. The Ollama image (`ollama/ollama:latest`) is pulled directly from Docker Hub by Azure when the Container App starts.

---

**The first-start delay** is the one gotcha — when the Container App boots for the first time, Ollama downloads ~2 GB of model weights inside the container. This takes 3–5 minutes. Use an Azure File Share volume instead of EmptyDir in production so weights are downloaded once and cached permanently.
