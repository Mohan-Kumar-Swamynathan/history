# துளிர் — Tamil Storytelling Channel

Fully automated Tamil storytelling YouTube channel ([@துளிர்-8](https://www.youtube.com/@%E0%AE%A4%E0%AF%81%E0%AE%B3%E0%AE%BF%E0%AE%B0%E0%AF%8D-8)).

**Single active pipeline:** `generate_video.py` → `src/pipelines/generate_video_v3.py`

**Flow:** Topic scoring → beat script → Edge TTS → Pexels stock video → subtitles → Shorts → YouTube upload

---

## Quick start (local)

```bash
git clone https://github.com/Mohan-Kumar-Swamynathan/history.git
cd history
pip install -r requirements.txt

export GEMINI_KEY="your-gemini-key"
export GROQ_API_KEY="your-groq-key"          # optional
export GITHUB_TOKEN="ghp_..."                # GitHub Models fallback
export PEXELS_API_KEY="your-pexels-key"      # required for video
export CLIENT_SECRETS_BASE64="..."
export YOUTUBE_TOKEN_BASE64="..."

# Long video + Shorts (no upload)
python generate_video.py --format long --daily-slot morning_long

# Upload to YouTube
python generate_video.py --format long --daily-slot morning_long --upload

# Shorts only
python generate_video.py --format short --upload
```

---

## Daily automation (GitHub Actions)

**Workflow:** Actions → **Thulir Unified Pipeline** (`thulir_unified.yml`)

| Slot | IST | Output |
|------|-----|--------|
| Morning | 07:00 | Long video + Shorts → YouTube |
| Evening | 19:00 | Long video + Shorts → YouTube |

Supporting workflows:
- `keepalive.yml` — daily repo ping
- `cleanup_artifacts.yml` — manual artifact cleanup

---

## Required secrets

| Secret | Purpose |
|--------|---------|
| `GEMINI_KEY` | LLM fallback |
| `GROQ_API_KEY` | LLM fallback |
| `GH_PAT_TOKEN` | GitHub Models (primary in CI) |
| `PEXELS_API_KEY` | Stock video + photo fallback |
| `YOUTUBE_TOKEN_BASE64` | YouTube upload |
| `CLIENT_SECRETS_BASE64` | OAuth refresh |

---

## Project layout

```
generate_video.py              # CLI entry point
src/pipelines/generate_video_v3.py
src/renderer/stock_video_engine.py
src/image_engine/image_engine.py
src/script/narrative_generator_v3.py
youtube_uploader.py            # OAuth upload helper
.github/workflows/thulir_unified.yml
```
