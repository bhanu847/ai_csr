# What You Need To Run This App

A single checklist of every external account, API key, and piece of local software this app depends on — and exactly where each one plugs in.

---

## 1. External accounts / API keys (the one paid piece)

| # | Service | What it's used for | Where to get it | Cost |
|---|---|---|---|---|
| 1 | **Twilio** | The phone number itself + real-time call audio streaming. The only piece that *must* touch the real phone network. | [twilio.com](https://www.twilio.com) console | Number rental (~$1–2/mo) + per-minute voice + Media Streams charges. Trial accounts need a payment method added before buying a number. |

The LLM, speech-to-text, and text-to-speech are all self-hosted now (section 2) — no Azure
account, no per-token or per-minute cloud billing for any of them.

**Twilio-specific setup** (needed only for real inbound calls, not for local dev of the dashboard):
- Buy a number: Console → Phone Numbers → Buy a number (Voice-capable)
- Set webhooks on that number: Voice webhook → `POST https://<your-public-url>/api/twilio/incoming`; Status callback → `POST https://<your-public-url>/api/twilio/status`
- Link the number to your tenant in the DB (no admin UI yet): `UPDATE tenants SET twilio_phone_number = '+1XXXXXXXXXX' WHERE slug = '<your-tenant-slug>';`
- Locally, a real public HTTPS URL is required — [ngrok](https://ngrok.com) (free tier is enough) gives you one: `ngrok http 8001`, then set that URL as `PUBLIC_SERVER_URL`.

---

## 2. Self-hosted / free pieces (no account needed)

| Piece | What it does | Software |
|---|---|---|
| **LLM** | Conversational replies + tool-calling during calls, call summaries, QA scoring, intent routing. `app/llm/client.py`. | [Ollama](https://ollama.com) running `qwen3:1.7b` (default — see note below; or any OpenAI-tool-calling-capable model) |
| **Embeddings** | Turns uploaded documents + caller questions into vectors for the knowledge-base search (RAG). | Ollama running `nomic-embed-text` |
| **Speech-to-text** | Transcribing the caller. `app/speech/stt.py`. | [faster-whisper](https://github.com/SYSTRAN/faster-whisper), runs on CPU |
| **Text-to-speech** | The AI's voice. `app/speech/tts.py`. | [piper-tts](https://github.com/OHF-Voice/piper1-gpl), runs on CPU |
| **Database** | Everything: calls, transcripts, agents, tenants, knowledge chunks. | PostgreSQL with the `pgvector` extension |
| **Backend** | The API + the WebSocket call-handling loop. | Python 3.14, FastAPI |
| **Frontend** | The dashboard. | Node.js + Angular |

**Ollama setup:**
- Install, then `ollama pull nomic-embed-text` and `ollama pull qwen3:1.7b` (or a model of your choice — anything that supports OpenAI-style tool calling through Ollama works; set `LLM_MODEL` to match).
- **Model size is a real latency tradeoff on CPU-only hardware**: `qwen3:1.7b` (the default) measured ~15-19s per call with thinking disabled (`LLM_DISABLE_THINKING=true`, also default) on this project's own CPU-only dev machine; `qwen3:8b` measured ~140-150s/call on the same hardware — unusable live. A GPU changes this substantially but hasn't been measured here. See `FAQ.md` §1 for the full measured breakdown.
- Set `OLLAMA_KEEP_ALIVE=-1` (or a long duration like `24h`) as an environment variable on the Ollama process/service itself. Ollama's OpenAI-compatible endpoint ignores a per-request `keep_alive`, so without this the model unloads after ~5 minutes idle and the next call pays a multi-second cold-start reload — bad on a live phone line.

**Piper voice setup:**
- Piper needs actual voice model files (`<voice-name>.onnx` + `<voice-name>.onnx.json`) in `PIPER_VOICES_DIR` (default `./voices`, under `backend/`) — not bundled in this repo.
- Download the voices you plan to use from the [Piper voices collection](https://huggingface.co/rhasspy/piper-voices) (e.g. `en_US-amy-medium`, `en_US-ryan-medium`, `en_GB-alan-medium`, `hi_IN-rohan-medium` — these specific names are what existing agents already have stored in `voice`).

---

## 3. Local software to install

- **Python 3.14**
- **Node.js + npm**
- **PostgreSQL** with `pgvector` extension available
- **[Ollama](https://ollama.com)**
- **[ngrok](https://ngrok.com)** (or another public-URL tunnel) — only needed to receive real phone calls locally

---

## 4. One-time setup steps

```bash
# 1. Ollama
ollama pull nomic-embed-text
ollama pull qwen3:1.7b
# then set OLLAMA_KEEP_ALIVE=-1 on the Ollama process/service (see section 2)

# 2. Python deps
cd backend
python -m venv venv
venv/Scripts/activate          # venv\Scripts\activate.bat on plain cmd
pip install -r requirements.txt

# 3. Configure backend/.env — see the full reference below.
#    Copy backend/.env.example to backend/.env and fill in the blanks.
#    You'll need: Piper voice files downloaded into ./voices (section 2),
#    and (for real calls) a Twilio number.

# 4. Database
alembic upgrade head

# 5. Train the instant-answer fast path (app/fastpath/) -- a few seconds,
#    produces backend/models/instant_answer.joblib. Re-run after editing
#    app/fastpath/data/faq_intents.json. Without this file, every turn just
#    falls through to the LLM -- it's a speed optimization, not required to
#    run the app.
python train_instant_answer_model.py

# 6. (optional) run the test suite against your configured DB
python -m pytest tests/

# 7. Start the backend
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

### LLM + embeddings (self-hosted via Ollama)
| Variable | Required | Notes |
|---|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` | No (defaults point at local Ollama) | `LLM_API_KEY` is unchecked by Ollama but the OpenAI SDK requires a non-empty value. |
| `LLM_MODEL` | No (default `qwen3:1.7b`) | Used for conversational replies/tool-calling AND the smaller structured-JSON calls (summaries, QA scoring, routing). Needs a matching `ollama pull`. See FAQ.md §1 for the measured latency tradeoff against `qwen3:8b` on CPU-only hardware. |
| `LLM_DISABLE_THINKING` | No (default `true`) | Disables Qwen3's chain-of-thought before answering — a real latency win on CPU (measured), at an unverified cost to tool-calling reliability. |
| `EMBEDDING_MODEL` | No (default `nomic-embed-text`) | Must have a matching `ollama pull`. |
| `EMBEDDING_DIM` | No (default `768`) | Must match the embedding model's native output size — baked into the DB column; changing it needs a migration. |

### Speech (self-hosted: faster-whisper STT, piper-tts TTS)
| Variable | Required | Notes |
|---|---|---|
| `STT_LANGUAGE` | No (default `en-US`) | Kept in locale form; `app/speech/stt.py` derives the bare ISO 639-1 code (`en`) faster-whisper actually wants. |
| `WHISPER_MODEL_SIZE` / `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | No (defaults `base`/`cpu`/`int8`) | Bigger model sizes (`small`, `medium`, ...) trade latency for accuracy. |
| `PIPER_VOICES_DIR` | No (default `./voices`) | Must contain the `.onnx`/`.onnx.json` files for every voice name an agent uses — see section 2. |
| `PIPER_DEFAULT_VOICE` | No (default `en_US-amy-medium`) | Used when an agent's `voice` field is empty. |

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
- [ ] `ollama pull nomic-embed-text` and `ollama pull qwen3:1.7b` (or your chosen `LLM_MODEL`) done, Ollama running, `OLLAMA_KEEP_ALIVE` set so it doesn't unload between calls
- [ ] Piper voice files (`.onnx` + `.onnx.json`) downloaded into `PIPER_VOICES_DIR` for every voice name an agent uses
- [ ] `python train_instant_answer_model.py` run at least once (optional — speeds up common questions, not required to run the app)
- [ ] `JWT_SECRET` set to a real random value (app refuses to start otherwise)
- [ ] `python -m pytest tests/` passes (optional, but a fast way to confirm Postgres/RLS/migrations are actually working before chasing a harder-to-diagnose runtime issue)
- [ ] Backend running (`uvicorn app.main:app --port 8001`), frontend running (`npm start`)
- [ ] *(only for real phone calls)* Twilio number bought, webhooks pointed at your public URL, number linked to a tenant in the DB

---

## 7. What this setup does and doesn't get you

Following every step above gets you a **running application** — it does not by itself mean the AI performs well on real healthcare calls. This project deliberately tracks that distinction; see `README.md` §12–13 and `docs/validation/evidence_requirements.md` for exactly what's been verified versus what's still unknown.
