# Adfluence

Turn live US news into ad creatives a media buying team can actually test.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![Status](https://img.shields.io/badge/status-active-3be0a0)

Adfluence pulls breaking US news every few hours, scores each story for virality, matches the strongest ones to ad niches like insurance, lending, home services, and health, and then generates the ad copy, a ready-to-test image, and a short video script for each. The whole thing runs on free tools and shows up in a live dashboard.

The point is simple: give the team a faster, news-driven starting point for creative, with a human still reviewing before anything goes live.

---

## What it does

- Fetches live news from Google News RSS and publisher feeds. Keyless and free.
- Scores virality with a transparent 0 to 100 heuristic (cross-outlet traction, recency, sentiment, headline triggers, source reach). No black box, every story shows its breakdown.
- Matches stories to ad niches only when the keywords genuinely support it, so connections are never fabricated.
- Writes grounded ad copy using the Gemini free tier, with a clean template fallback when no key is set.
- Builds a production-style creative: an AI generated, in-context image with the headline and CTA composited on top so the text stays crisp.
- Drafts a 15 second UGC style video script for each creative.
- Serves everything in a dashboard you can filter by niche, with the top stories per niche.
- Re-syncs on a schedule so the feed stays current on its own.

## How it works

```mermaid
flowchart LR
    A[Live news RSS] --> B[Virality scoring]
    B --> C[Niche matching]
    C --> D[Ad copy]
    D --> E[Creatives: image + video script]
    E --> F[Dashboard]
```

1. **Fetch** breaking US news across niche queries and publisher feeds.
2. **Score** each story for virality with a transparent, bounded heuristic.
3. **Match** the top stories to an ad niche, only when the keywords back it up.
4. **Generate** grounded ad copy, an image creative, and a video script.
5. **Serve** it all in a dashboard, refreshed on a schedule.

## Tech stack

Python, FastAPI, APScheduler (scheduled syncs), SQLite, feedparser, VADER (sentiment), Google Gemini (free tier copy), Cloudflare Workers AI / FLUX (images), Pillow (ad compositing). No paid services required.

## Ad niches

Stories are grouped into six broad verticals, each backed by a keyword model:

- Insurance, Finance and Legal
- Home Services
- Health and Supplements
- Financial Publishing and Investing
- Education and Career
- B2B Lead Gen

## Project structure

```
adfluence/
├── app.py            # FastAPI server + scheduler + API routes
├── pipeline.py       # fetch -> score -> match -> copy -> creatives -> store
├── news_fetcher.py   # multi-source RSS fetching
├── virality.py       # transparent virality scoring
├── correlator.py     # niche matching + ad copy
├── creatives.py      # image prompt, FLUX render, Pillow ad compositor, video script
├── gemini_client.py  # Gemini REST client (text)
├── db.py             # SQLite layer
├── config.py         # niches + all settings
├── static/           # dashboard (index.html)
└── requirements.txt
```

## Setup

```bash
git clone https://github.com/hansika-grover/adfluence
cd adfluence
pip install -r requirements.txt
cp .env.example .env     # add your keys (optional, see below)
python app.py
```

Then open http://127.0.0.1:8000 and hit **Sync now**.

It runs with zero keys out of the box using the honest template fallback. Add keys to unlock AI copy and images.

## Configuration

Everything lives in `.env` (copy it from `.env.example`):

| Variable | What it does |
|---|---|
| `GEMINI_API_KEY` | Free Gemini key for AI ad copy and scripts. Leave blank for templates. |
| `IMAGE_RENDER` | `none` or `cloudflare`. Set to `cloudflare` to render images. |
| `CF_ACCOUNT_ID` / `CF_API_TOKEN` | Cloudflare Workers AI creds (free, no card) for image rendering. |
| `MAX_IMAGES_PER_SYNC` | Cap on images rendered per sync. |
| `TOP_N` / `TOP_PER_NICHE` | How many stories to surface globally and per niche. |
| `REFRESH_HOURS` | How often to re-sync the news. |

## Notes

- Images need Cloudflare (free, no credit card). Without it you still get the copy, the image prompt, and the video script, just no rendered picture.
- The virality score is a transparent heuristic, not a trained model. It is meant to rank, not predict exact reach.
- Some niches (health, finance, legal) are heavily regulated. Adfluence keeps copy grounded, but everything should get human review before it runs as an ad.

## License

MIT
