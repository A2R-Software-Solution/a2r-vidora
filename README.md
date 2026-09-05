   # VidoraAI

> AI-powered video intelligence platform — understand, search, summarize, and later create short-form content from long-form videos.

## 1. Product Overview

VidoraAI is a web-based AI video intelligence platform where a user provides a YouTube video URL and can interact with the video's content.

### Core MVP capabilities

- Accept a YouTube video URL.
- Analyze the video's audio/content.
- Generate a timestamped transcript.
- Semantically index transcript chunks.
- Ask natural-language questions about the video.
- Return concise answers with relevant timestamps.
- Generate video summaries.
- Temporarily retain transcript/embeddi   ng data an  d automatically remove it after approximately 24 hours.
- Do not permanently store the original YouTube video.

### Future capability

- Identify useful moments from a long-form video.
- Generate short vertical reels/shorts.
- Add captions and format clips for short-form platforms.

The Reel/Short generation feature is outside the first MVP.

## 2. Architecture

```text
User
  |
  v
React Frontend
  |
  v
Vercel
  |
  v
Firebase Python Cloud Functions
  |
  +------------------+------------------+
  |                  |                  |
  v                  v                  v
yt-dlp             MiniLM             Groq
  |              Embeddings          STT + LLM
  |                  |
  +---------> Supabase PostgreSQL <----+
                  + pgvector
                       |
                       v
               Temporary video data
                       |
                    ~24 hours
                       |
                       v
                     DELETE
```

## 3. Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| Frontend | React | Web interface |
| Frontend Hosting | Vercel | Host web application |
| Backend | FastAPI | API/application layer |
| Backend Runtime | Firebase Python Cloud Functions | Serverless deployment |
| YouTube Extraction | yt-dlp | Retrieve/process YouTube media |
| Media Processing | FFmpeg, if required | Audio/video processing |
| STT | Groq Whisper | Production/API transcription |
| Local STT Testing | Whisper | Local/free testing |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Semantic embeddings |
| Embedding Runtime | CPU | Avoid GPU infrastructure |
| Database | PostgreSQL | Structured data |
| Vector Search | pgvector | Similarity search |
| Database Platform | Supabase | Managed PostgreSQL + pgvector |
| ORM | SQLAlchemy | Database abstraction |
| DB Driver | asyncpg | Async PostgreSQL |
| Migrations | Alembic | Schema migrations |
| LLM | Groq GPT-OSS 20B | Answers/summaries |
| RAG Framework | None initially | Lightweight custom retrieval |

## 4. Backend Architecture

The backend follows Separation of Concerns.

```text
HTTP Request
     |
     v
API Routes
     |
     v
Services / Business Logic
     |
     +----------+-----------+-----------+
     |          |           |           |
     v          v           v           v
Database   YouTube       Embedding     Groq
Layer      Integration   Integration    Integration
```

- **API:** HTTP endpoints, validation, responses and routing.
- **Services:** Core business logic and workflows.
- **Integrations:** yt-dlp, Groq and embedding-model integrations.
- **Database:** SQLAlchemy engine/session, models and pgvector operations.
- **Schemas:** Pydantic request/response contracts.
- **Core:** Configuration and logging.

## 5. Planned API

### Analyze video

```http
POST /videos/analyze
```

```json
{
  "youtube_url": "https://www.youtube.com/watch?v=..."
}
```

Workflow:

```text
URL → validate → yt-dlp → audio → STT → timestamped transcript
→ chunking → embeddings → PostgreSQL + pgvector
```

### Ask about video

```http
POST /videos/{video_id}/ask
```

```text
Question
   ↓
MiniLM embedding
   ↓
pgvector similarity search
   ↓
Relevant transcript chunks
   ↓
Groq GPT-OSS 20B
   ↓
Answer + timestamps
```

Summary/chapters endpoints can be added after the core workflow is stable.

## 6. Video Processing

Users do **not** upload videos. They provide a YouTube URL.

```text
YouTube URL
    ↓
yt-dlp
    ↓
Required audio/media
    ↓
STT
    ↓
Timestamped transcript
```

### Storage policy

- Original YouTube video is not permanently stored.
- Temporary media is deleted after processing.
- Transcript chunks are temporary.
- Embeddings are temporary.
- Video metadata is temporary.
- Target retention is approximately 24 hours.

## 7. STT

Production/API transcription:

```text
Groq Whisper
```

Local/free testing:

```text
Whisper
```

Timestamps must be preserved.

Example:

```text
00:00 - 00:18
Introduction...

18:42 - 20:30
Third Battle of Panipat...
```

## 8. Embeddings

Model:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Embedding dimension:

```text
384
```

Pipeline:

```text
Transcript → Chunking → MiniLM → 384-dimensional vector → pgvector
```

The same model embeds user questions.

MiniLM runs on CPU for the MVP. No GPU is planned initially.

## 9. Retrieval / RAG Strategy

A large RAG framework is not required.

We use:

```text
PostgreSQL + pgvector
```

Each video has its own transcript chunks and embeddings.

```text
Question
   ↓
Query embedding
   ↓
pgvector
   ↓
Relevant chunks from requested video
   ↓
LLM
```

RAGWire, LangChain or another large RAG framework is intentionally excluded from the initial MVP.

## 10. LLM

Current LLM:

```text
Groq GPT-OSS 20B
```

The model receives the user question, relevant transcript chunks and timestamps, and returns a concise answer with relevant timestamp(s).

## 11. Database

Database:

```text
Supabase PostgreSQL
```

Vector extension:

```text
pgvector
```

The `vector` extension has already been enabled.

### Initial entities

#### `videos`

```text
id
youtube_id
youtube_url
title
duration
status
created_at
expires_at
```

#### `transcript_chunks`

```text
id
video_id
chunk_text
start_time
end_time
embedding (vector(384))
```

Tables will **not** be manually created in Supabase SQL Editor. Schema management uses:

```text
SQLAlchemy Models
       ↓
Alembic Migration
       ↓
Supabase PostgreSQL
```

## 12. Async Architecture

The backend is async-first where practical.

```text
FastAPI
   ↓
SQLAlchemy Async
   ↓
asyncpg
   ↓
Supabase PostgreSQL
```

Async I/O is used for database operations, HTTP/API requests and Groq requests.

CPU/blocking workloads such as model inference, yt-dlp and FFmpeg must be handled appropriately rather than assuming `async def` makes them non-blocking.

## 13. Environment & Secrets

Local variables:

```text
functions/.env
```

Example:

```env
DATABASE_URL=postgresql+asyncpg://...
GROQ_API_KEY=...
ENVIRONMENT=development
```

`.env` must never be committed.

Production secrets should eventually use Google Secret Manager/Firebase-managed secrets.

## 14. Deployment

### Frontend

```text
React → Vercel
```

Firebase Hosting is intentionally not used for the frontend.

### Backend

```text
Firebase Python Cloud Functions → FastAPI
```

### Database

```text
Supabase → PostgreSQL + pgvector
```

### AI

```text
Groq → Whisper STT + GPT-OSS 20B
```

## 15. yt-dlp, MiniLM & FFmpeg

### yt-dlp

Python dependency installed in the Firebase Python Functions environment.

### MiniLM

Sentence Transformers and the model run inside the Firebase Function environment on CPU.

A cold start may require model loading when a new serverless instance is created.

### FFmpeg

The actual FFmpeg executable is different from a Python wrapper package. The exact YouTube audio extraction pipeline will first be tested to determine whether the binary is required.

If required, deployment will be adapted to Firebase Functions' runtime constraints.

## 16. Data Retention

```text
Video analysis
      ↓
Transcript + embeddings
      ↓
User uses video
      ↓
~24 hours
      ↓
Automatic deletion
```

No permanent source-video storage is planned.

## 17. Security & Abuse Protection

Planned controls:

- YouTube URL validation
- Maximum video duration
- Per-user/IP rate limits
- Maximum questions per video/user
- Maximum concurrent processing
- Request timeouts
- Safe temporary-file handling
- Secret management
- Logging and error handling
- Usage/cost limits

## 18. Cost Strategy

| Component | Initial Plan |
|---|---|
| Firebase Cloud Functions | Usage-based |
| Firebase Blaze | Already enabled |
| Supabase | Free tier initially |
| PostgreSQL | Included |
| pgvector | Included |
| MiniLM | No separate API cost |
| Vercel | Free tier initially |
| Groq STT | Usage-based |
| Groq LLM | Usage-based |
| Domain | Annual cost |
| AWS Lightsail | Not used initially |

The goal is to avoid a fixed always-on server cost during the MVP.

## 19. Firebase Setup Completed

Firebase project:

```text
Display Name: VidoraAI
Project ID: vidoraai-2bbce
```

Completed:

- Firebase CLI login
- Project selection
- Firebase initialization
- Python Cloud Functions selected
- Python runtime configured for 3.11
- Local `functions/venv` configured with Python 3.11
- Firebase Functions dependencies installed

## 20. Current Dependencies

Target `functions/requirements.txt`:

```text
firebase_functions~=0.5.0
fastapi
uvicorn
yt-dlp
sentence-transformers
python-dotenv
SQLAlchemy
alembic
pgvector
asyncpg
```

`psycopg2-binary` was removed because the project uses async PostgreSQL connectivity through `asyncpg`.

## 21. Alembic

Alembic has been initialized:

```text
functions/
└── alembic/
    ├── versions/
    ├── env.py
    ├── README
    └── script.py.mako
```

Also:

```text
functions/alembic.ini
```

The generated `env.py` is being adapted for:

- `.env` loading
- Async SQLAlchemy
- asyncpg
- SQLAlchemy model metadata
- Autogenerated migrations

## 22. Target Project Structure

```text
vidoraai/
│
├── functions/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── videos.py
│   │   │   │   └── chat.py
│   │   │   └── router.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── logging.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── video.py
│   │   │   └── transcript.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── video.py
│   │   │   └── chat.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── video_service.py
│   │   │   ├── transcript_service.py
│   │   │   ├── embedding_service.py
│   │   │   └── chat_service.py
│   │   └── integrations/
│   │       ├── __init__.py
│   │       ├── youtube.py
│   │       ├── groq.py
│   │       └── embeddings.py
│   ├── alembic/
│   │   └── versions/
│   ├── main.py
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── .env
│   └── .gitignore
├── frontend/
├── README.md
└── .gitignore
```

## 23. Separation of Concerns

| Layer | Responsibility |
|---|---|
| `api` | HTTP routes |
| `schemas` | Pydantic validation/contracts |
| `services` | Business logic |
| `integrations` | External APIs/tools |
| `models` | SQLAlchemy models |
| `db` | Database engine/session/Base |
| `core` | Configuration/logging |
| `alembic` | Database migrations |
| `main.py` | Firebase entry point/application wiring |

`main.py` should not contain business logic.

## 24. Development Roadmap

### Phase 1 — Infrastructure

- [x] Firebase project
- [x] Blaze plan
- [x] Python Functions
- [x] Python 3.11
- [x] Local venv
- [x] Core dependencies
- [x] Supabase project
- [x] pgvector extension
- [x] Transaction Pooler
- [x] Alembic initialization

### Phase 2 — Database

- [ ] SQLAlchemy Base
- [ ] Async database session
- [ ] Application configuration
- [ ] Alembic async configuration
- [ ] Video model
- [ ] Transcript chunk model
- [ ] Initial migration
- [ ] Supabase migration test
- [ ] Vector index/query setup

### Phase 3 — Video Ingestion

- [ ] YouTube URL validation
- [ ] yt-dlp integration
- [ ] Audio extraction
- [ ] STT integration
- [ ] Timestamped transcript
- [ ] Temporary file cleanup

### Phase 4 — Embeddings

- [ ] Transcript chunking
- [ ] MiniLM embedding service
- [ ] Store embeddings
- [ ] Query embeddings
- [ ] pgvector similarity search

### Phase 5 — AI Answers

- [ ] Groq integration
- [ ] Retrieval context construction
- [ ] Prompt design
- [ ] Answer generation
- [ ] Timestamp formatting

### Phase 6 — API

- [ ] `/videos/analyze`
- [ ] `/videos/{video_id}/ask`
- [ ] Summary endpoint
- [ ] Health endpoint
- [ ] Error handling
- [ ] Rate limiting

### Phase 7 — Frontend

- [ ] Connect Vercel frontend
- [ ] URL submission
- [ ] Processing state
- [ ] Video workspace
- [ ] Ask Video UI
- [ ] Timestamp navigation
- [ ] Summary UI

### Phase 8 — Production

- [ ] 24-hour cleanup
- [ ] Temporary-file cleanup
- [ ] Secret management
- [ ] Logging
- [ ] Monitoring
- [ ] Cost controls
- [ ] Rate limits
- [ ] Firebase deployment
- [ ] Production testing

### Phase 9 — Video to Reels

After Ask Video is stable:

```text
Long Video
    ↓
Transcript
    ↓
LLM identifies strong segments
    ↓
Select timestamps
    ↓
FFmpeg clips
    ↓
9:16 conversion
    ↓
Captions
    ↓
Short/Reel
```

## 25. MVP Scope

### Included

- YouTube URL input
- Video analysis
- Timestamped transcript
- Semantic search
- Ask Video
- Relevant timestamps
- Summary
- Temporary data
- 24-hour cleanup
- Web application

### Excluded Initially

- Mandatory authentication
- Permanent video storage
- Large RAG framework
- GPU server
- Load balancer
- Multi-instance architecture
- Automatic Reel generation
- Complex subscriptions/billing
- Large-scale analytics

## 26. Key Architecture Decisions

1. Web first, not native mobile.
2. Vercel for frontend hosting.
3. Firebase Python Cloud Functions for backend.
4. FastAPI for the backend framework.
5. Supabase PostgreSQL + pgvector for database/vector search.
6. SQLAlchemy + asyncpg + Alembic for database access/migrations.
7. MiniLM on CPU for embeddings.
8. Groq Whisper for API STT.
9. Groq GPT-OSS 20B for answer generation.
10. No large RAG framework initially.
11. No permanent source-video storage.
12. Temporary transcript/embedding data expires after approximately 24 hours.
13. No fixed $12/month Lightsail server initially.
14. No load balancer for MVP.
15. Deployment uses usage limits and cost controls.

## 27. Immediate Next Step

```text
SQLAlchemy Base
      ↓
Async DB Session
      ↓
Models
      ↓
Alembic env.py
      ↓
Initial Migration
      ↓
Supabase PostgreSQL
```

Then:

```text
yt-dlp
   ↓
STT
   ↓
Transcript
   ↓
Chunking
   ↓
MiniLM
   ↓
pgvector
   ↓
Groq
   ↓
Ask Video
```

## 28. Project Principle

Build with a production-oriented architecture without unnecessary infrastructure or frameworks.

```text
Simple
→ Correct
→ Testable
→ Cost-controlled
→ Production-ready
```
