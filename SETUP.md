# What You Need To Run This App

A single checklist of every external account, API key, and piece of local software this app depends on — and exactly where each one plugs in. Written after the stack moved from fully self-hosted to a hybrid (hosted LLM + hosted STT, everything else still self-hosted/free).

---

## 1. External accounts / API keys (the paid pieces)

| # | Service | What it's used for | Where to get it | Cost |
|---|---|---|---|---|
| 1 | **Anthropic (Claude)** | The LLM — conversational replies during calls, call summaries, QA scoring, intent routing. `app/llm/client.py`. | [console.anthropic.com](https://console.anthropic.com) → API Keys | Real, per-token. Default model `claude-opus-5`; see cost note below. |
| 2 | **Deepgram** | Speech-to-text — transcribes the caller's audio. `app/speech/stt.py`. | [console.deepgram.com](https://console.deepgram.com) | Real, per-minute. Free trial credit on signup. |
| 3 | **Twilio** | The phone number itself + real-time call audio streaming. The only piece that *must* touch the real phone network. | [twilio.com](https://www.twilio.com) console | Number rental (~$1–2/mo) + per-minute voice + Media Streams charges. Trial accounts need a payment method added before buying a number. |

**Cost-tuning note:** `claude-opus-5` is the strongest available model. For this app's actual workload — short (max 3 sentences), latency-sensitive conversational replies at potentially high call volume — `claude-sonnet-5` or `claude-haiku-4-5` are likely far cheaper and just as fast. Switch by changing one value: `ANTHROPIC_MODEL` in `backend/.env`.

**Twilio-specific setup** (needed only for real inbound calls, not for local dev of the dashboard):
- Buy a number: Console → Phone Numbers → Buy a number (Voice-capable)
- Set webhooks on that number: Voice webhook → `POST https://<your-public-url>/api/twilio/incoming`; Status callback → `POST https://<your-public-url>/api/twilio/status`
- Link the number to your tenant in the DB (no admin UI yet): `UPDATE tenants SET twilio_phone_number = '+1XXXXXXXXXX' WHERE slug = '<your-tenant-slug>';`
- Locally, a real public HTTPS URL is required — [ngrok](https://ngrok.com) (free tier is enough) gives you one: `ngrok http 8001`, then set that URL as `PUBLIC_SERVER_URL`.

---

## 2. Self-hosted / free pieces (no account needed)

| Piece | What it does | Software |
|---|---|---|
| **Embeddings** | Turns uploaded documents + caller questions into vectors for the knowledge-base search (RAG). Still self-hosted — only chat moved to Claude. | [Ollama](https://ollama.com) running `nomic-embed-text` |
| **Text-to-speech** | Synthesizes the AI's spoken replies. | [Piper](https://github.com/rhasspy/piper) (runs in-process, no server) |
| **Database** | Everything: calls, transcripts, agents, tenants, knowledge chunks. | PostgreSQL with the `pgvector` extension |
| **Backend** | The API + the WebSocket call-handling loop. | Python 3.14, FastAPI |
| **Frontend** | The dashboard. | Node.js + Angular |

---

## 3. Local software to install

- **Python 3.14**
- **Node.js + npm**
- **PostgreSQL** with `pgvector` extension available
- **[Ollama](https://ollama.com)** — for embeddings only now, not chat
- **[ngrok](https://ngrok.com)** (or another public-URL tunnel) — only needed to receive real phone calls locally

---

## 4. One-time setup steps

```bash
# 1. Ollama — embeddings model only (chat no longer runs through Ollama)
ollama pull nomic-embed-text

# 2. Piper voices — at least the default one
cd backend
mkdir voices && cd voices
python -m piper.download_voices en_US-amy-medium
cd ..

# 3. Python deps
python -m venv venv
venv/Scripts/activate          # venv\Scripts\activate.bat on plain cmd
pip install -r requirements.txt

# 4. Configure backend/.env — see the full reference below.
#    Copy backend/.env.example to backend/.env and fill in the blanks.

# 5. Database
alembic upgrade head

# 6. Start the backend
uvicorn app.main:app --port 8001 --reload
```

```bash
# Frontend, in a separate terminal
cd frontend
npm install
npm start          # http://localhost:4200
```

Register a tenant/admin in the dashboard, create an agent in Agent Studio, and you're running — real phone calls additionally need the Twilio steps in section 1.

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

### LLM (Claude — the conversational brain)
| Variable | Required | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes, for calls to work | From console.anthropic.com. |
| `ANTHROPIC_MODEL` | No (default `claude-opus-5`) | Swap to `claude-sonnet-5` or `claude-haiku-4-5` for a much cheaper/faster fit for short voice replies. |
| `ANTHROPIC_EFFORT` | No (default `low`) | Thinking depth. Raise (`medium`/`high`) if replies feel shallow on harder questions — costs more latency. |

### Speech-to-text (Deepgram)
| Variable | Required | Notes |
|---|---|---|
| `DEEPGRAM_API_KEY` | Yes, for calls to work | From console.deepgram.com. |
| `STT_LANGUAGE` | No (default `en`) | Passed through to Deepgram. |
| `WHISPER_MODEL_SIZE` / `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | No | **Unused now** — leftover from the self-hosted faster-whisper setup, kept only in case of a rollback. |

### Embeddings (still self-hosted via Ollama)
| Variable | Required | Notes |
|---|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | No (defaults point at local Ollama) | `LLM_MODEL` is vestigial now (chat moved to Claude) — only the embeddings client still uses this base URL/key. |
| `EMBEDDING_MODEL` | No (default `nomic-embed-text`) | Must have a matching `ollama pull`. |
| `EMBEDDING_DIM` | No (default `768`) | Must match the embedding model's native output size — baked into the DB column; changing it needs a migration. |

### Text-to-speech (Piper)
| Variable | Required | Notes |
|---|---|---|
| `PIPER_VOICES_DIR` | No (default `./voices`) | Directory holding downloaded `.onnx` voice files. |
| `PIPER_DEFAULT_VOICE` | No (default `en_US-amy-medium`) | Must match a downloaded voice file exactly. |

### Barge-in / interruption tuning
| Variable | Required | Notes |
|---|---|---|
| `BARGE_IN_MS` | No (default 200) | Consecutive ms of caller speech during AI playback before it counts as a real interruption. |
| `BARGE_IN_RMS_THRESHOLD` | No (default 750) | Loudness bar for that speech — deliberately higher than normal turn-taking to resist speakerphone echo false-triggers. |

### Concurrency
| Variable | Required | Notes |
|---|---|---|
| `BLOCKING_THREAD_POOL_SIZE` | No (default 200) | Thread pool shared by every blocking STT/LLM/TTS/DB call. Removes an accidental ~12-thread Python default; does **not** by itself mean this many calls can run at once — real capacity depends on Claude/Deepgram/Twilio rate limits. |

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
- [ ] At least one Piper voice downloaded into `PIPER_VOICES_DIR`
- [ ] `ANTHROPIC_API_KEY` set
- [ ] `DEEPGRAM_API_KEY` set
- [ ] `JWT_SECRET` set to a real random value (app refuses to start otherwise)
- [ ] Backend running (`uvicorn app.main:app --port 8001`), frontend running (`npm start`)
- [ ] *(only for real phone calls)* Twilio number bought, webhooks pointed at your public URL, number linked to a tenant in the DB
