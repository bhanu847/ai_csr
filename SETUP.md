# What You Need To Run This App

A single checklist of every external account, API key, and piece of local software this app depends on — and exactly where each one plugs in.

---

## 1. External accounts / API keys (the paid pieces)

| # | Service | What it's used for | Where to get it | Cost |
|---|---|---|---|---|
| 1 | **Azure OpenAI** | The LLM — conversational replies during calls, call summaries, QA scoring, intent routing. `app/llm/client.py`. | [Azure Portal](https://portal.azure.com) → create an Azure OpenAI resource → deploy a chat model in Azure AI Studio | Real, per-token. Varies by model/region — check the Azure OpenAI pricing page for your region. |
| 2 | **Azure AI Speech** | Speech-to-text (transcribing the caller) *and* text-to-speech (the AI's voice, neural voices). `app/speech/stt.py`, `app/speech/tts.py`. One resource covers both. | [Azure Portal](https://portal.azure.com) → create a Speech resource | Real, per-minute, billed separately for STT vs. TTS — check the Azure AI Speech pricing page. |
| 3 | **Twilio** | The phone number itself + real-time call audio streaming. The only piece that *must* touch the real phone network. | [twilio.com](https://www.twilio.com) console | Number rental (~$1–2/mo) + per-minute voice + Media Streams charges. Trial accounts need a payment method added before buying a number. |

**Twilio-specific setup** (needed only for real inbound calls, not for local dev of the dashboard):
- Buy a number: Console → Phone Numbers → Buy a number (Voice-capable)
- Set webhooks on that number: Voice webhook → `POST https://<your-public-url>/api/twilio/incoming`; Status callback → `POST https://<your-public-url>/api/twilio/status`
- Link the number to your tenant in the DB (no admin UI yet): `UPDATE tenants SET twilio_phone_number = '+1XXXXXXXXXX' WHERE slug = '<your-tenant-slug>';`
- Locally, a real public HTTPS URL is required — [ngrok](https://ngrok.com) (free tier is enough) gives you one: `ngrok http 8001`, then set that URL as `PUBLIC_SERVER_URL`.

**Azure OpenAI-specific setup:**
- Create the resource, then in **Azure AI Studio** deploy a chat-capable model (e.g. `gpt-4o`) under a **deployment name** you choose — that deployment name, not the model name, is what goes in `AZURE_OPENAI_DEPLOYMENT`.
- New deployments have a tokens-per-minute quota that may be too low for real call volume — request a quota increase in Azure AI Studio if you hit rate limits under load.

**Azure AI Speech-specific setup:**
- One resource, one key + region, used for both STT and TTS — no separate deployment step like OpenAI needs.
- Agent voices are set in Agent Studio as any name from the [Azure neural voice gallery](https://speech.microsoft.com/portal/voicegallery) (e.g. `en-US-JennyNeural`).

---

## 2. Self-hosted / free pieces (no account needed)

| Piece | What it does | Software |
|---|---|---|
| **Embeddings** | Turns uploaded documents + caller questions into vectors for the knowledge-base search (RAG). The only piece still self-hosted — everything voice/chat-related moved to Azure. | [Ollama](https://ollama.com) running `nomic-embed-text` |
| **Database** | Everything: calls, transcripts, agents, tenants, knowledge chunks. | PostgreSQL with the `pgvector` extension |
| **Backend** | The API + the WebSocket call-handling loop. | Python 3.14, FastAPI |
| **Frontend** | The dashboard. | Node.js + Angular |

---

## 3. Local software to install

- **Python 3.14**
- **Node.js + npm**
- **PostgreSQL** with `pgvector` extension available
- **[Ollama](https://ollama.com)** — for embeddings only
- **[ngrok](https://ngrok.com)** (or another public-URL tunnel) — only needed to receive real phone calls locally

---

## 4. One-time setup steps

```bash
# 1. Ollama — embeddings model only (chat/speech run through Azure)
ollama pull nomic-embed-text

# 2. Python deps
cd backend
python -m venv venv
venv/Scripts/activate          # venv\Scripts\activate.bat on plain cmd
pip install -r requirements.txt

# 3. Configure backend/.env — see the full reference below.
#    Copy backend/.env.example to backend/.env and fill in the blanks.
#    You'll need: an Azure OpenAI resource + chat deployment, an Azure
#    AI Speech resource, and (for real calls) a Twilio number.

# 4. Database
alembic upgrade head

# 5. Start the backend
uvicorn app.main:app --port 8001 --reload
```

```bash
# Frontend, in a separate terminal
cd frontend
npm install
npm start          # http://localhost:4200
```

Register a tenant/admin in the dashboard, create an agent in Agent Studio (voice = any Azure neural voice name), and you're running — real phone calls additionally need the Twilio steps in section 1.

---

## 5. `backend/.env` reference — every variable

### Database
| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | Runtime connection, low-privilege `app_user` role. Must NOT be a superuser — Row-Level Security tenant isolation is silently bypassed for a superuser/BYPASSRLS role. |
| `MIGRATIONS_DATABASE_URL` | Yes | Superuser/owner connection, used only by Alembic. Never used by the running app. |
| `DB_POOL_SIZE` / `DB_POOL_MAX_OVERFLOW` | No (default 20 / 20) | Concurrent DB connections this process can hold. Must stay under Postgres's own `max_connections` (default 100). |

### Auth
| Variable | Required | Notes |
|---|---|---|
| `JWT_SECRET` | Yes | Long random string. Rejected at startup if it's the placeholder or under 32 characters. |
| `JWT_ALGORITHM` | No (default `HS256`) | |
| `JWT_EXPIRES_MINUTES` | No (default 720) | |

### LLM (Azure OpenAI — the conversational brain)
| Variable | Required | Notes |
|---|---|---|
| `AZURE_OPENAI_API_KEY` | Yes, for calls to work | From your Azure OpenAI resource. |
| `AZURE_OPENAI_ENDPOINT` | Yes | `https://<your-resource>.openai.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT` | Yes | The **deployment name** you chose in Azure AI Studio — not a model name like `gpt-4o`. |
| `AZURE_OPENAI_API_VERSION` | No (default `2024-10-21`) | |

### Speech (Azure AI Speech — STT and TTS)
| Variable | Required | Notes |
|---|---|---|
| `AZURE_SPEECH_KEY` | Yes, for calls to work | From your Azure Speech resource. |
| `AZURE_SPEECH_REGION` | Yes | e.g. `eastus`. |
| `AZURE_DEFAULT_VOICE` | No (default `en-US-JennyNeural`) | Used when an agent's `voice` field is empty. |
| `STT_LANGUAGE` | No (default `en-US`) | Azure locale format (`en-US`, not `en`). |
| `WHISPER_MODEL_SIZE` / `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | No | **Unused** — leftover from the earlier self-hosted faster-whisper setup, kept only in case of a rollback. |
| `PIPER_VOICES_DIR` / `PIPER_DEFAULT_VOICE` | No | **Unused** — leftover from the earlier self-hosted Piper setup, kept only in case of a rollback. |

### Embeddings (still self-hosted via Ollama)
| Variable | Required | Notes |
|---|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | No (defaults point at local Ollama) | Vestigial for chat (that's Azure OpenAI now) — kept only because the embeddings client reuses this base URL/key. |
| `EMBEDDING_MODEL` | No (default `nomic-embed-text`) | Must have a matching `ollama pull`. |
| `EMBEDDING_DIM` | No (default `768`) | Must match the embedding model's native output size — baked into the DB column; changing it needs a migration. |

### Barge-in / interruption tuning
| Variable | Required | Notes |
|---|---|---|
| `BARGE_IN_MS` | No (default 200) | Consecutive ms of caller speech during AI playback before it counts as a real interruption. |
| `BARGE_IN_RMS_THRESHOLD` | No (default 750) | Loudness bar for that speech — deliberately higher than normal turn-taking to resist speakerphone echo false-triggers. |

### Concurrency
| Variable | Required | Notes |
|---|---|---|
| `BLOCKING_THREAD_POOL_SIZE` | No (default 200) | Thread pool shared by every blocking STT/LLM/TTS/DB call. Removes an accidental ~12-thread Python default; does **not** by itself mean this many calls can run at once — real capacity depends on your Azure quota and Twilio limits. |

### Telephony (Twilio)
| Variable | Required | Notes |
|---|---|---|
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | Yes, for real calls | From the Twilio console. |
| `PUBLIC_SERVER_URL` | Yes, for real calls | Your public HTTPS URL (ngrok for local dev). Used as the Twilio webhook base and, as `wss://`, the live audio WebSocket URL. |

### Misc
| Variable | Required | Notes |
|---|---|---|
| `CORS_ORIGINS` | No (default `http://localhost:4200,http://127.0.0.1:4200`) | Comma-separated allowed frontend origins. |

---

## 6. Quick "is everything configured" checklist

- [ ] Postgres running, `pgvector` extension available, `alembic upgrade head` applied
- [ ] `ollama pull nomic-embed-text` done, Ollama running
- [ ] Azure OpenAI resource created, a chat model deployed, `AZURE_OPENAI_*` vars set
- [ ] Azure AI Speech resource created, `AZURE_SPEECH_KEY`/`AZURE_SPEECH_REGION` set
- [ ] `JWT_SECRET` set to a real random value (app refuses to start otherwise)
- [ ] Backend running (`uvicorn app.main:app --port 8001`), frontend running (`npm start`)
- [ ] *(only for real phone calls)* Twilio number bought, webhooks pointed at your public URL, number linked to a tenant in the DB
