# AI Car Mechanic Chatbot — Backend

Django + Django REST Framework backend for an AI car mechanic chatbot. Users describe car problems in chat (text / image / audio / video), the bot asks focused follow-up questions, produces a structured diagnosis (likely issue, confidence, drive-safety advice, recommended service), and lets the user book a mechanic appointment.

**Core design principle:** a deterministic rule engine handles everything it can — Gemini is called **only** as a last-resort natural-language fallback. See [Architecture](#architecture).

- Frontend repo: [Instant-mechanic-frontend](https://github.com/Nikhilraghuwanshi04/Instant-mechanic-frontend)
- Stack: Django 6.1 · DRF 3.18 · SQLite · python-dotenv
- Tests: 76 passing (unit + API integration)

---

## Table of contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Tech stack](#tech-stack)
4. [Project structure](#project-structure)
5. [Data models](#data-models)
6. [Local setup](#local-setup)
7. [Environment variables](#environment-variables)
8. [API reference](#api-reference)
9. [Error handling](#error-handling)
10. [Testing](#testing)
11. [Security measures](#security-measures)
12. [Deployment](#deployment)

---

## Features

- **Conversational diagnosis** — symptom detection with 8 rule-based symptom categories, one focused follow-up question at a time, only then a diagnosis.
- **Structured diagnosis output** — likely issue, reasoning, confidence (low/medium/high), whether it is safe to drive, next step, recommended service.
- **Media uploads** — images (JPEG/PNG/WEBP), audio (MP3/WAV/OGG/MP4/WebM), video (MP4/MOV/WEBM) validated by magic bytes, not by the client-declared type.
- **Mechanic booking** — one booking per diagnosis, unique human-readable reference (`BK-XXXXXXXX`), phone + date validation.
- **Conversation history** — list and full restore of any past conversation (messages, media, diagnosis, booking).
- **AI provenance tracking** — every bot message and diagnosis records `generated_by` (`rule_engine` or `gemini`), making the rule-engine-first design visible and auditable.
- **Graceful AI degradation** — with no Gemini key, or when Gemini fails/times out, the app keeps working on rules alone; users never see an internal error.

## Architecture

The graded centerpiece: **use traditional backend logic wherever possible, minimize AI/API usage.**

```
User message ──► DRF view ──► rule_engine (knowledge base match)
                                  │
                    understood? ──┤ yes ──► reply / structured diagnosis   (generated_by = rule_engine)
                                  │
                                  └── no (needs_nlu) ──► gemini_client
                                                             │ success ──► AI reply / diagnosis  (generated_by = gemini)
                                                             └ failure/timeout/disabled ──► rule-engine fallback reply
```

### Rule engine (first line, `chatbot/services/`)

- `knowledge_base.py` — 8 symptom categories, ordered by priority: **brakes → overheating → steering/suspension → battery/electrical → transmission → warning lights → engine noise → AC**. Each category contains symptom keywords, follow-up questions, explanation text and recommended service.
- `rule_engine.py` — matches user text against category keywords, tracks which categories a conversation is already about, and asks the next unanswered follow-up question instead of jumping to a diagnosis.
- `diagnosis_engine.py` — merges all user messages, picks the primary + secondary category (dangerous categories win), collects safety flags, and computes confidence with a simple transparent rule: number of distinct primary symptoms matched (1 term → low, 2 → medium, 3+ → high). No match at all → `needs_nlu = true`.

### Gemini (last-resort fallback only)

`gemini_client.py` is the single door to the AI API, and it is called from exactly **two** places:

| Situation | What happens |
|---|---|
| Chat message the rule engine cannot classify | Gemini asks one natural follow-up question (`chat_reply`) |
| Diagnosis requested for an unclassifiable conversation | Gemini returns a structured diagnosis (`diagnose`) |

Guardrails built into the client:

- API key lives only in backend `.env` — never in code, never sent to the frontend.
- Every failure returns `None`; the caller falls back to the rule-engine reply. **Exceptions never escape** and users never see stack traces.
- Retry (2 retries) + model failover across `GEMINI_MODEL` → `GEMINI_FALLBACK_MODELS` on `429/503` (per-model free-tier quota / high-demand spikes).
- Hard timeout on every call (default 30 s) so our API never hangs.
- AI JSON output is validated field by field before saving (`_clean_diagnosis`) — conservative defaults on anything malformed (`confidence → low`, `can_drive → false`).
- Prompts treat the conversation as data, not instructions, and cap the transcript at the last 20 messages.

**Gemini is NOT called for:** uploads (file validation/storage is fully deterministic), conversation history, bookings, or any message the rule engine understands.

## Tech stack

| Layer | Choice |
|---|---|
| Framework | Django 6.1.1 |
| API | Django REST Framework 3.18 |
| CORS | django-cors-headers |
| Config | python-dotenv (`.env` → environment variables) |
| Database | SQLite |
| AI (optional fallback) | Google Gemini via REST (`requests`) |
| HTTP client | requests |

## Project structure

```
backend/
├── manage.py
├── requirements.txt
├── .env.example              # template — copy to .env and fill in
├── config/                   # Django project (settings, root URLs, wsgi/asgi)
│   ├── settings.py           # env-driven: DEBUG, ALLOWED_HOSTS, CORS, limits, Gemini
│   └── urls.py               # mounts chatbot.urls under /api/ + serves /media/ in DEBUG
└── chatbot/                  # the single app
    ├── models.py             # Conversation, Message, MediaUpload, Diagnosis, Booking
    ├── serializers.py        # request validation + response shaping
    ├── views.py              # all 8 endpoints
    ├── urls.py               # /api/... routes
    ├── exception_handler.py  # unhandled errors → clean JSON 500 (never HTML)
    ├── migrations/
    ├── services/             # ← the deterministic brain + AI fallback
    │   ├── knowledge_base.py
    │   ├── rule_engine.py
    │   ├── diagnosis_engine.py
    │   ├── media_validator.py
    │   └── gemini_client.py
    └── tests/                # 76 tests (unit + API integration)
```

## Data models

| Model | Purpose | Notable fields |
|---|---|---|
| `Conversation` | One chat thread | `title`, `status` (active/diagnosed/booked/closed), `state` (JSON scratchpad), vehicle info |
| `Message` | One chat bubble | `role` (user/assistant), `content`, `generated_by` (**user / rule_engine / gemini**) |
| `MediaUpload` | One uploaded file | `file`, `media_type` (image/audio/video), `original_name`, `size_bytes`, `mime_type`, `analysis_status` |
| `Diagnosis` | Structured diagnosis | `likely_issue`, `reasoning`, `confidence`, `can_drive`, `next_step`, `recommended_service`, `generated_by` |
| `Booking` | Mechanic appointment | `booking_ref` (unique), one-to-one with `Diagnosis`, `customer_name`, `phone`, `preferred_date`, `status` |

## Local setup

Requires Python 3.11+.

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # then edit .env (a Gemini key is optional)

python manage.py migrate
python manage.py runserver 8010
```

Health check: `curl http://127.0.0.1:8010/api/health/` → `{"status": "ok", "service": "ai-car-mechanic-backend"}`

The app is fully functional without a `GEMINI_API_KEY` — the rule engine covers most conversations; Gemini is only an NLU fallback.

## Environment variables

All configuration is read from `backend/.env` (see `.env.example`). **`.env` is gitignored — never commit it.**

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev placeholder | Django secret key — set a fresh random value in production |
| `DJANGO_DEBUG` | `True` | Set `False` in production |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated hostnames allowed to serve the app |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated frontend origins allowed to call the API |
| `GEMINI_API_KEY` | *(empty)* | Google AI Studio key. Empty → Gemini disabled, rules still work |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Primary Gemini model |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.5-flash,gemini-3.7-flash` | Tried in order on 429/503 (each model has its own free-tier quota) |
| `GEMINI_TIMEOUT_SECONDS` | `30` | Per-request timeout |
| `MAX_IMAGE_MB` | `10` | Max image upload size |
| `MAX_AUDIO_MB` | `15` | Max audio upload size |
| `MAX_VIDEO_MB` | `25` | Max video upload size |

## API reference

Base URL locally: `http://127.0.0.1:8010`. All endpoints are under `/api/` and return JSON. All are public (no auth — per assignment scope).

Quick summary:

| Method | Endpoint | Purpose | Gemini? |
|---|---|---|---|
| GET | `/api/health/` | Liveness check | No |
| POST | `/api/chat/` | Send a message, get bot reply | Only if unclassifiable |
| POST | `/api/upload/` | Upload image/audio/video | No — fully deterministic |
| POST | `/api/diagnosis/` | Get structured diagnosis | Only if unclassifiable |
| POST | `/api/booking/` | Book a mechanic for a diagnosis | No |
| GET | `/api/booking/{id}/` | Fetch one booking's current status | No |
| GET | `/api/conversations/` | History sidebar list | No |
| GET | `/api/conversations/{id}/` | Restore a full conversation | No |

> The brief lists 5 required APIs. `GET /api/conversations/` and `GET /api/conversations/{id}/` are **additional** read-only endpoints the frontend needs for the conversation-history sidebar; no extra AI usage is involved.

---

### 1. `POST /api/chat/`

Send the user's message; get the bot's reply.

**Request** (JSON):

```json
{ "message": "My brakes squeal when I stop.", "conversation_id": 3 }
```

| Field | Type | Required | Validation |
|---|---|---|---|
| `message` | string | yes | non-blank, ≤ 2000 characters |
| `conversation_id` | integer | no | positive int; omit to start a new conversation |

**Response 201** (new conversation) / **200** (existing conversation):

```json
{
  "conversation_id": 3,
  "conversation_title": "My brakes squeal when I stop.",
  "user_message": { "id": 12, "role": "user", "content": "My brakes squeal when I stop.", "generated_by": "user", "created_at": "2026-10-02T18:00:00Z" },
  "reply": { "id": 13, "role": "assistant", "content": "Brake noise is usually... Does the noise happen only while braking, or also while driving?", "generated_by": "rule_engine", "created_at": "2026-10-02T18:00:00Z" }
}
```

`reply.generated_by` tells you exactly who answered: `rule_engine` (the normal path) or `gemini` (NLU fallback — only when the rule engine reports `needs_nlu`).

**Errors:** `400` blank/too-long message, invalid or closed conversation · `404` conversation not found · `405` wrong method.

---

### 2. `POST /api/upload/`

Upload an image/audio/video the user attached; the file is validated and stored, a `MediaUpload` record is created.

**Request** (multipart form-data):

| Field | Type | Required | Validation |
|---|---|---|---|
| `file` | file | yes | see table below — real type detected from magic bytes, not the client MIME |
| `conversation_id` | integer | no | positive int; omit to start a new conversation titled `Upload: <filename>` |

| Type | Allowed formats | Max size |
|---|---|---|
| image | JPEG, PNG, WEBP | `MAX_IMAGE_MB` (default 10 MB) |
| audio | MP3, WAV, OGG, MP4 (audio), WebM (audio) | `MAX_AUDIO_MB` (default 15 MB) |
| video | MP4, MOV, WebM | `MAX_VIDEO_MB` (default 25 MB) |

**Response 201/200:**

```json
{
  "conversation_id": 3,
  "conversation_title": "Upload: brake-pad.jpg",
  "media": {
    "id": 5, "file": "http://127.0.0.1:8010/media/uploads/brake-pad.jpg",
    "media_type": "image", "original_name": "brake-pad.jpg", "size_bytes": 84213,
    "mime_type": "image/jpeg", "analysis_status": "pending",
    "created_at": "2026-10-02T18:05:00Z"
  }
}
```

**Gemini usage: none.** Validation and storage are 100% deterministic — no AI call is made for uploads. `analysis_status` (`pending`/`analyzed`/`skipped`) is reserved for future AI analysis; the current version deliberately keeps uploads AI-free.

**Errors:** `400` unsupported type, file too large, empty file, filename > 255 chars, closed conversation · `404` conversation not found · `405` wrong method.

---

### 3. `POST /api/diagnosis/`

Ask for a structured diagnosis of a conversation. Intended to be called once the user and bot have discussed the problem (the frontend shows a "Get Diagnosis" action).

**Request** (JSON):

```json
{ "conversation_id": 3 }
```

| Field | Type | Required | Validation |
|---|---|---|---|
| `conversation_id` | integer | yes | positive int, must exist, must contain ≥ 1 user message |

**Response 201:**

```json
{
  "conversation_id": 3,
  "conversation_status": "diagnosed",
  "diagnosis": {
    "id": 7,
    "likely_issue": "Worn brake pads (metal-on-metal contact)",
    "reasoning": "Matched brake squeal symptoms in 2 messages; the noise while braking points to pad wear.",
    "confidence": "medium",
    "can_drive": false,
    "next_step": "Have the brake pads inspected before driving long distances.",
    "recommended_service": "Brake pad replacement",
    "generated_by": "rule_engine",
    "summary": { "categories": ["brakes"], "safety_flags": [], "user_messages_analyzed": 3, "source": "rule_engine" },
    "created_at": "2026-10-02T18:10:00Z"
  }
}
```

**How it is produced (rule engine first):**

1. All user messages are matched against the knowledge base; the highest-priority (most dangerous) matched category becomes the primary one.
2. Confidence is a transparent rule on distinct primary symptoms: 1 → `low`, 2 → `medium`, 3+ → `high`.
3. `can_drive` is conservative — dangerous categories and unresolved uncertainty → `false`.
4. If **nothing** matches (`needs_nlu`), Gemini is asked once; if it fails, a safety-first low-confidence fallback diagnosis is returned. `generated_by` records which path produced the result.

**Errors:** `400` no user messages yet / closed conversation / missing conversation_id · `404` conversation not found · `405` wrong method.

---

### 4. `POST /api/booking/`

Book a mechanic appointment for a diagnosis (the user confirms in the UI first).

**Request** (JSON):

```json
{ "diagnosis_id": 7, "customer_name": "Nikhil R.", "phone": "+91 98765 43210", "preferred_date": "2026-10-05" }
```

| Field | Type | Required | Validation |
|---|---|---|---|
| `diagnosis_id` | integer | yes | positive int, must exist |
| `customer_name` | string | yes | non-blank, ≤ 100 chars |
| `phone` | string | yes | `+` optional, 7–20 digits/spaces/dashes |
| `preferred_date` | date | yes | `YYYY-MM-DD`, not in the past |

**Response 201:**

```json
{
  "conversation_id": 3,
  "conversation_status": "booked",
  "booking": {
    "id": 9, "booking_ref": "BK-4F8A2C1D", "diagnosis_id": 7, "conversation_id": 3,
    "likely_issue": "Worn brake pads (metal-on-metal contact)",
    "customer_name": "Nikhil R.", "phone": "+91 98765 43210",
    "preferred_date": "2026-10-05", "status": "pending",
    "created_at": "2026-10-02T18:15:00Z", "updated_at": "2026-10-02T18:15:00Z"
  }
}
```

**Gemini usage: none.** The rule engine's `recommended_service` is what the user books; no AI call is needed to book.

**Errors:** `400` validation (missing name, bad phone, past date) · `404` diagnosis not found · `409` a booking already exists for this diagnosis (one booking per diagnosis) · `405` wrong method.

---

### 5. `GET /api/booking/{id}/`

Fetch a single booking with its current status (frontend polls/refreshes after creation).

**Response 200:**

```json
{ "booking": { "id": 9, "booking_ref": "BK-4F8A2C1D", "status": "pending", "...": "same shape as POST /api/booking/" } }
```

**Errors:** `404` booking not found · `405` wrong method.

---

### 6. `GET /api/conversations/` *(extra — history sidebar)*

List all conversations, newest activity first, with a message count and preview (single annotated query — no N+1).

**Response 200:**

```json
{
  "conversations": [
    {
      "id": 3, "title": "My brakes squeal when I stop.", "status": "diagnosed",
      "created_at": "2026-10-02T18:00:00Z", "updated_at": "2026-10-02T18:10:00Z",
      "message_count": 6, "last_message_preview": "Brake noise is usually..."
    }
  ]
}
```

**Errors:** `405` wrong method.

---

### 7. `GET /api/conversations/{id}/` *(extra — restore history)*

Restore everything about one conversation: messages, media, latest diagnosis, booking (if any). The frontend uses this when you click a sidebar entry.

**Response 200:**

```json
{
  "conversation": { "id": 3, "title": "My brakes squeal when I stop.", "status": "booked", "message_count": 6, "last_message_preview": "..." },
  "messages": [ { "id": 12, "role": "user", "content": "...", "generated_by": "user", "created_at": "..." } ],
  "media": [ { "id": 5, "file": "http://.../media/uploads/brake-pad.jpg", "media_type": "image", "...": "..." } ],
  "diagnosis": { "id": 7, "likely_issue": "...", "...": "..." },
  "booking": { "id": 9, "booking_ref": "BK-4F8A2C1D", "...": "..." }
}
```

`diagnosis` and `booking` are `null` when they don't exist yet. Media file URLs are returned absolute so the frontend can render them directly.

**Errors:** `404` conversation not found · `405` wrong method.

---

## Error handling

- Validation errors use DRF shapes: `{"detail": "..."}` for object-level, `{"field": ["message"]}` for field-level — both are user-friendly sentences, never internal details.
- A custom DRF exception handler converts any unhandled exception into a clean JSON `500` (`{"detail": "Something went wrong..."}`) — clients never receive an HTML traceback, regardless of `DEBUG`.
- `DEBUG=False` in production hides framework internals from responses by default.
- Frontend-safe rule: error messages are written for end users (e.g. `"Preferred date cannot be in the past."`), while technical detail goes to server logs only.

## Testing

76 tests, all offline-deterministic (Gemini calls mocked; uses an in-memory test database and a temp media folder — the dev database and `media/` are untouched). Full suite runs in ~0.1 s.

```bash
source venv/bin/activate
python manage.py test chatbot
# Ran 76 tests ... OK
```

| Area | File | Tests |
|---|---|---|
| Rule engine (categories, follow-ups, danger priority) | `tests/test_rule_engine.py` | 14 |
| Diagnosis engine (confidence, safety, needs_nlu) | `tests/test_diagnosis_engine.py` | 10 |
| Media validator (magic bytes, size, spoofing) | `tests/test_media_validator.py` | 12 |
| `POST /api/chat/` incl. error matrix | `tests/test_api_chat.py` | 13 |
| `POST /api/upload/` incl. error matrix | `tests/test_api_upload.py` | 6 |
| `POST /api/diagnosis/` | `tests/test_api_diagnosis.py` | 8 |
| `POST /api/booking/` + `GET /api/booking/{id}/` | `tests/test_api_booking.py` | 7 |
| `GET /api/conversations/` + detail | `tests/test_api_history.py` | 6 |

## Security measures

Mapped to the assignment's security requirements:

- **No secrets in the frontend** — the Gemini key exists only in backend `.env`; the frontend never sees or sends it.
- **No `.env` in version control** — `.gitignore` excludes `.env` / `.env.*`; only placeholder `.env.example` is committed.
- **File validation** — every upload's real type is detected from magic bytes (client MIME type is not trusted), type must be on an allowlist, size is capped per media type, empty files and over-long filenames are rejected.
- **No internal errors exposed** — user-facing messages are plain sentences; unhandled exceptions become generic JSON `500`s; Gemini failures silently fall back to rule-engine behaviour.
- **CORS configured explicitly** — only origins listed in `CORS_ALLOWED_ORIGINS` may call the API.
- **AI output treated as untrusted** — Gemini's JSON is validated field by field with conservative defaults; prompts instruct the model to treat chat text as data, not instructions.

## Deployment

Production checklist (AWS free tier / any VM):

1. Set `.env` on the server: `DJANGO_DEBUG=False`, a fresh `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS=<server-host>`, `CORS_ALLOWED_ORIGINS=https://<vercel-app>.vercel.app`, `GEMINI_API_KEY=<real key>`.
2. `python manage.py migrate` + `python manage.py collectstatic`.
3. Run behind a WSGI server (gunicorn) with a reverse proxy (nginx) serving `/media/` (uploads) and `/static/` and forwarding `/api/` to Django.

The frontend expects this backend at `NEXT_PUBLIC_API_BASE_URL` (see the frontend repo).
