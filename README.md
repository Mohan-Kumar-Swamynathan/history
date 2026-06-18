# துளிர் — Tamil Storytelling Channel

Fully automated Tamil storytelling YouTube channel (Almost Everything style).

**Active pipeline:** `generate_video.py` → `src/pipelines/` (unified framework)

**Pipeline:** Topic scoring → 24-beat story script → Edge TTS → whiteboard animation → subtitles → Shorts → YouTube upload

---

## Quick start (துளிர் unified pipeline)

```bash
git clone https://github.com/Mohan-Kumar-Swamynathan/history.git
cd history
pip install -r requirements.txt

export GEMINI_KEY="your-gemini-key"
export GROQ_API_KEY="your-groq-key"          # optional
export GITHUB_TOKEN="ghp_..."                # GitHub Models fallback
export CLIENT_SECRETS_BASE64="..."
export YOUTUBE_TOKEN_BASE64="..."

# Long video (8-12 min) + Shorts bundle
python generate_video.py --format long --upload

# Shorts only (30-60s)
python generate_video.py --format short --upload

# Generate without upload
python generate_video.py --format short
```

### Daily automation (GitHub Actions)

Workflow: **Actions → Thulir Unified Pipeline** (`thulir_unified.yml`)

| Slot | IST | Output |
|------|-----|--------|
| Morning | 09:00 | ~5 min long video + Shorts → YouTube |
| Evening | 19:00 | ~5 min long video + Shorts → YouTube |

Legacy workflows are **disabled** (manual trigger only).

---

## Legacy: வரலாறு விழிப்பு (History bot)

The old history documentary pipeline (`bot.py`, Pexels footage) is kept for reference but no longer runs on schedule.

```bash
python3 bot.py --list
python3 bot.py --skip-upload
```

---

Each daily run automatically discovers a fresh Tamil history topic:

1. **Wikipedia On This Day** — English + Tamil Wikipedia events for today's date
2. **Google News RSS** — recent history headlines
3. **LLM picks best topic** — Gemini chooses the most engaging Tamil-relevant angle
4. **LLM invent fallback** — if nothing fits, generates a fresh original topic

Topics are deduplicated for 30 days via `scheduler_state.json`.

| Flag | Behavior |
|------|----------|
| *(default)* | Discover trending topic from Wikipedia + news |
| `--static` | Use hardcoded 30-topic bank rotation |
| `--topic N` | Manual pick from bank (overrides discovery) |
| `--list` | Show all 30 hardcoded topics |

Topic sources logged as: `wikipedia`, `news`, `llm_generated`, `static_bank`, `manual_bank`

---

## Quick start (local)

```bash
git clone https://github.com/Mohan-Kumar-Swamynathan/history.git
cd history
pip install -r requirements.txt

export GEMINI_KEY="your-gemini-key"
export PEXELS_API_KEY="your-pexels-key"
export CLIENT_SECRETS_BASE64="..."
export YOUTUBE_TOKEN_BASE64="..."
export GITHUB_TOKEN="ghp_..."   # PAT with models:read for LLM fallback
export GROQ_API_KEY="..."      # optional tertiary LLM fallback

# List all topics
python3 bot.py --list

# Run today's trending topic (generates + uploads to YouTube)
python3 bot.py

# Use hardcoded 30-topic bank instead
python3 bot.py --static

# Generate without uploading
python3 bot.py --skip-upload

# Run specific topic
python3 bot.py --topic 3

# Use female voice
python3 bot.py --topic 5 --voice female_emotional

# Script + audio only (no video render)
python3 bot.py --topic 0 --skip-video

# Force a specific LLM provider
python3 bot.py --llm gemini
python3 bot.py --llm github
python3 bot.py --llm groq
```

---

## GitHub Actions — Daily Automation

Runs daily at **14:15 UTC = 19:45 IST**. Generates video and **uploads to YouTube automatically**.

### Setup (one-time)

Add these secrets in **Settings → Secrets and variables → Actions**:

| Secret | Purpose |
|--------|---------|
| `GEMINI_KEY` | Primary LLM for scripts + metadata |
| `PEXELS_API_KEY` | Stock video background clips |
| `CLIENT_SECRETS_BASE64` | YouTube OAuth client config |
| `YOUTUBE_TOKEN_BASE64` | YouTube OAuth token |
| `GROQ_API_KEY` | Optional tertiary LLM fallback |

`GITHUB_TOKEN` is provided automatically for GitHub Models fallback (requires `models: read` permission in workflow).

### Generate YouTube credentials

```bash
pip install google-auth-oauthlib google-api-python-client
python3 scripts/encode_youtube_credentials.py --client-secrets path/to/client_secret.json
```

Copy the printed base64 values into GitHub Secrets.

### Manual trigger

Go to **Actions → Tamil History — Daily Video Pipeline → Run workflow**

Options: topic index, voice, skip video, skip upload.

---

## LLM Fallback Chain

1. **Gemini** (`GEMINI_KEY`) — primary
2. **GitHub Models** (`GITHUB_TOKEN`) — fallback, free in Actions
3. **Groq** (`GROQ_API_KEY`) — optional tertiary fallback

---

## Optimal Upload Schedule

Computed for Tamil audience timezones (IST 55%, Singapore 10%, UK 10%, USA 6%):

| Day | Upload Time (IST) |
|-----|-------------------|
| Saturday | 19:45 (best) |
| Sunday | 19:43 |
| Friday | 19:42 |

Upload at 19:45 IST so YouTube indexes the video before the 20:15 peak viewer window.

---

## File structure

```
history/
├── bot.py                    # Main pipeline
├── topic_discovery.py        # Wikipedia + news + LLM topic picker
├── llm_client.py             # Gemini → GitHub Models → Groq
├── pexels_client.py          # Stock footage fetcher
├── youtube_uploader.py       # YouTube upload + thumbnail
├── scheduler.py              # Topic discovery + static bank + optimal time
├── bgm_generator.py          # Standalone BGM generator
├── scripts/
│   └── encode_youtube_credentials.py
├── upload_state.json         # Upload history (tracked)
└── .github/workflows/
    └── daily_video.yml       # Daily cron + auto-upload
```
