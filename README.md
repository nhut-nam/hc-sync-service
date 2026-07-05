# Customer Support Sync & Assistant

A lightweight sync job and support bot built on Google Gemini (using the managed File Search Store RAG tool) to index help center articles from support.optisigns.com.

---

## Deliverables

- **Setup & Local Runs**: See instructions below.
- **Dockerfile**: Runs the main sync using `docker run -e API_KEY=... main.py` and exits cleanly.
- **Link to Daily Job Logs**: [Cloud Sync Logs Dashboard](https://dashboard.render.com/cron/optibot-sync-job/logs) (or equivalent platform dashboard where the container scheduled run output is captured).
- **Sanity Check Screenshot**: Refer to [screenshot.png](screenshot.jpg) in the repository root showing the correct grounded response with citations.

---

## Setup & Local Run

### 1. Installation
Ensure Python 3.12+ is installed:
```bash
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

### 2. Configure Environment
Create a `.env` file in the project root:
```env
API_KEY=your_gemini_api_key
```

### 3. Run Locally
- **Sync all articles**:
  ```bash
  python main.py
  ```
- **Sync limited articles (Quick testing)**:
  ```bash
  python main.py --limit 35
  ```
- **Ask a question directly (RAG query only)**:
  ```bash
  python src/assistant.py --ask "How do I add a YouTube video?"
  ```

---

## RAG & Chunking Strategy

- **Embedding Model**: `models/gemini-embedding-001`.
- **Chunking**: Uses whitespace-based tokenization.
  - `max_tokens_per_chunk`: **300** tokens (maintains procedural context).
  - `max_overlap_tokens`: **30** tokens (~10% overlap safety).
- **Stateless Cloud Sync**: Delta logic is completely stateless. Filenames are formatted as `<slug>_id_<article_id>_u_<epoch_timestamp>.md`. The job lists files in the store to calculate the delta (added, updated, skipped) and removes stale or legacy documents dynamically without needing local `state.json` persistence.

---

## Docker Deployment
```bash
# Build the image
docker build -t optibot-sync .

# Run the container once
docker run -e API_KEY=your_api_key optibot-sync
```
Schedule this container to run once per day (e.g. at 2 AM UTC) on platforms like Railway, Render, or AWS ECS.
