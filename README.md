# Google AI Mode API

**Self-hosted JSON API for Google's AI Mode (`udm=50`), built for SEO / GEO research.**

🇹🇷 [Türkçe README](README.tr.md)

Google does not publish an official AI Mode API. This service runs headless Chromium
(Playwright) inside Docker, opens the AI Mode result page, waits for the answer to finish
streaming, and returns structured JSON.

It is built around one question that classic rank tracking cannot answer:

> **When Google's AI answers this query, whose content does it cite — and is that us?**

---

## What you get back

```jsonc
{
  "status": "ok",
  "query": "best crm software",
  "answer": "## Top options\n- **HubSpot** …",     // markdown
  "blocks": [                                       // structured, claim-level
    { "type": "paragraph", "text": "…", "links": [ { "url": "…", "domain": "hubspot.com" } ] }
  ],
  "citations": [                                    // in order of appearance
    { "position": 1, "title": "…", "url": "https://…", "domain": "hubspot.com" }
  ],
  "domains": [                                      // share of voice per domain
    { "domain": "hubspot.com", "citations": 3, "first_position": 1, "share": 0.375, "urls": ["…"] }
  ],
  "follow_ups": ["How much does a CRM cost?"],      // Google's suggested next questions
  "tracked_domains": [ { "domain": "yoursite.com", "cited": true, "positions": [2] } ],
  "tracked_brands": [ { "brand": "YourBrand", "mentioned": true, "count": 2, "contexts": ["…"] } ],
  "stats": { "characters": 1840, "words": 260, "citation_count": 8, "unique_domains": 5, "block_count": 12 },
  "source_url": "https://www.google.com/search?q=…&udm=50",
  "device": "desktop", "hl": "en", "gl": "US",
  "resolved_location": "Istanbul,Turkey",
  "cached": false, "truncated": false, "elapsed_ms": 24310
}
```

`blocks[].links` is the part that matters most: it maps **which claim cites which source**,
instead of dumping one flat link list for the whole answer.

---

## Quick start

```bash
git clone https://github.com/TurkerYakup/google-ai-mode-api.git
cd google-ai-mode-api
cp .env.example .env          # set GAM_API_KEY if you expose this beyond localhost
docker compose up -d --build
```

```bash
curl http://127.0.0.1:8000/health
```

Interactive docs (Swagger): <http://127.0.0.1:8000/docs>

> The port binds to `127.0.0.1` only. **Set `GAM_API_KEY` before** changing that in
> `docker-compose.yml`.

### One query

```bash
curl -s -X POST http://127.0.0.1:8000/v1/query \
  -H 'Content-Type: application/json' \
  -d '{
        "query": "best crm software",
        "location": "Istanbul,Turkey",
        "device": "desktop",
        "track_domains": ["yoursite.com", "competitor.com"],
        "track_brands": ["YourBrand"]
      }'
```

Or quickly via GET:

```bash
curl "http://127.0.0.1:8000/v1/query?q=best+crm&track_domains=yoursite.com,competitor.com"
```

### Async tasks (recommended)

An AI Mode answer takes 30–90 s to stream. Most HTTP clients give up first. Submit a task,
get an ID, poll later — or have the result POSTed to your webhook:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tasks/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"crm comparison","tag":"weekly-scan","postback_url":"https://your-system/webhook"}'
# → {"task_id":"a1b2…","status":"queued","poll_url":"/v1/tasks/a1b2…"}

curl -s http://127.0.0.1:8000/v1/tasks/a1b2…
```

### Keyword set

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tasks/batch \
  -H 'Content-Type: application/json' \
  -d '{
        "queries": ["crm software", "crm pricing", "free crm"],
        "track_domains": ["yoursite.com"],
        "location": "Ankara,Turkey",
        "tag": "crm-cluster"
      }'
```

Tasks run **sequentially** with `GAM_BATCH_DELAY` seconds between them. That is deliberate —
firing them in parallel is the fastest way to get a verification page from Google.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Status, browser pools, pending task count |
| `POST` | `/v1/query` | Single query, synchronous |
| `GET` | `/v1/query?q=…` | Single query, synchronous, convenience form |
| `POST` | `/v1/batch` | Keyword list, synchronous (use tasks for >5) |
| `POST` | `/v1/tasks/query` | Queue one query → `202` + `task_id` |
| `POST` | `/v1/tasks/batch` | Queue a keyword list |
| `GET` | `/v1/tasks/{id}` | Task status and result |
| `GET` | `/v1/tasks?status=done` | List tasks |
| `DELETE` | `/v1/cache` | Flush the result cache |
| `POST` | `/v1/browser/restart` | Restart Chromium |
| `GET` | `/v1/debug/html?q=…` | Raw HTML, for fixing selectors (off by default) |
| `GET` | `/v1/debug/screenshot?q=…` | Full-page PNG, base64 |

When `GAM_API_KEY` is set, every `/v1/*` route requires an `X-API-Key` header.

---

## Request parameters

| Field | Alias | Default | Purpose |
|---|---|---|---|
| `query` | `keyword`, `q` | — | The question to ask |
| `hl` | `language_code` | `GAM_HL` | Interface language (`tr`, `en`, `de`) |
| `gl` | `country_code` | `GAM_GL` | Country code (`TR`, `US`) |
| `google_domain` | `se_domain` | `www.google.com` | e.g. `www.google.co.uk` |
| `location` | `location_name` | — | Canonical location → `uule`. e.g. `Istanbul,Turkey` |
| `uule` | — | — | Pass your own uule; overrides `location` |
| `device` | — | `desktop` | `desktop` \| `mobile` — separate profile, UA and viewport |
| `track_domains` | — | `[]` | Did these domains get cited (subdomains included) |
| `track_brands` | — | `[]` | Do these strings appear in the answer, with context |
| `include_blocks` | — | `true` | Structured block output |
| `include_html` | — | `false` | Raw HTML of the answer container |
| `include_screenshot` | — | `false` | Base64 PNG, for reports |
| `include_follow_ups` | — | `true` | Suggested follow-up questions |
| `timeout` | — | `GAM_ANSWER_TIMEOUT` | 5–300 s |
| `cache` | — | `true` | Reuse a recent identical query |

The aliases exist so an existing DataForSEO integration can point here with minimal edits:
`keyword`, `language_code`, `location_name` and `se_domain` are all accepted.

---

## Configuration

Everything is a `GAM_`-prefixed environment variable (`.env`). Full list in
[.env.example](.env.example). The ones that matter:

| Variable | Default | Note |
|---|---|---|
| `GAM_API_KEY` | *(empty)* | Empty means **authentication disabled** |
| `GAM_POOL_SIZE` | `1` | Concurrent tabs. Do not go above 2 |
| `GAM_ANSWER_TIMEOUT` | `90` | Max wait for the answer to finish streaming |
| `GAM_STABLE_FOR` | `1.6` | Text unchanged this long ⇒ streaming finished |
| `GAM_CACHE_TTL` | `900` | `0` disables the cache |
| `GAM_BATCH_DELAY` | `2.5` | Pause between queries in a batch |
| `GAM_CONSENT_CHOICE` | `reject` | Cookie banner default: **reject all** |
| `GAM_ANSWER_SELECTORS` | *(see config)* | Override as a JSON array when Google's DOM shifts |

---

## How this compares to commercial APIs

There are real vendors selling exactly this, and they are a reasonable choice if you'd
rather buy than run. Roughly, as of **August 2026** — verify current pricing yourself:

| Provider | AI Mode support | Indicative price | Model |
|---|---|---|---|
| [DataForSEO](https://dataforseo.com/pricing/serp/google-ai-mode-serp-api) | `serp/google/ai_mode`, live + standard (normal/high priority), advanced + HTML endpoints | from **$0.004 / page** (live), $50 minimum top-up | Pay as you go |
| [SerpApi](https://serpapi.com/google-ai-mode-api) | `engine=google_ai_mode`; `text_blocks`, `references`, shopping/local results, inline images & videos, multi-turn follow-ups, markdown output | from **$75 / mo** for 5 000 searches, 100 free | Subscription |
| [Bright Data](https://brightdata.com/blog/web-data/best-serp-apis) | SERP API | ~**$3 / 1 000** results, plans from $499/mo | PAYG + subscription |
| [Oxylabs](https://oxylabs.io/blog/best-serp-api) | SERP Scraper API, pay-per-success | ~**$0.80–1.00 / 1 000** | Subscription tiers |
| **This project** | AI Mode only | infrastructure cost only | Self-hosted |

**Buy instead of running this if** you need thousands of queries a day, guaranteed uptime,
a proxy pool, and someone to call when Google changes its markup.

**Run this if** you want a few hundred queries a day for your own research, want the raw
HTML and screenshots, want to add your own metrics, or simply don't want a per-query bill.
It has no proxy pool, no SLA, and one IP address.

Features on the roadmap, openly borrowed from the vendors above: multi-turn follow-ups in a
single session, extraction of shopping / local / video blocks, and a token-efficient
`output=md` response format.

---

## Known limitations

By design, and stated plainly:

- **Single IP, no proxy pool.** Query hard enough and Google shows a verification page; the
  API then returns `503 blocked`. For volume, put a residential proxy in front via
  `GAM_BROWSER_ARGS` (`--proxy-server=…`).
- **Expect to be challenged on day one.** A cold profile on an unknown IP often gets the
  "unusual traffic" page within the first few requests — this is normal, not a bug. Solve it
  once by hand (see *Maintaining the browser profile*); the resulting cookie usually settles
  things down. `GAM_BROWSER_CHANNEL=chromium` matters here: Playwright otherwise runs its
  `headless-shell` binary, which is flagged noticeably faster than the full browser.
- **CAPTCHAs are not solved.** When a verification page appears the request fails, on
  purpose. `scripts/login.py` lets you clear it by hand in a visible browser.
- **Selectors are fragile.** Google's DOM is obfuscated and changes often. Hence three
  layers: a configurable selector list → a "largest text block" heuristic → `/v1/debug/html`
  to find a new one. The `extracted_by` field tells you which layer fired.
- **The `uule` encoding is unofficial.** It is the community-derived format; Google may
  ignore it. If location precision is critical, verify the output or pass your own `uule`.
- **Tasks live in memory.** A restart clears the queue. Add Redis/Postgres if you need
  durability.
- **AI Mode doesn't always trigger.** Google skips the AI answer for some queries; you get
  `502 no_answer`.

---

## Maintaining the browser profile

Cookies and session state live in the `profile` Docker volume, under
`/data/profile/{desktop,mobile}`. A named volume is used so the image's `app:app`
ownership carries over — the app does not run as root and could not write to a fresh
bind-mounted host directory.

If you hit a verification page, prepare the profile by hand on a machine with a screen and
copy it in:

```bash
pip install playwright && playwright install chromium
python scripts/login.py --profile ./profile-desktop     # solve it in the window, then close
docker compose cp ./profile-desktop google-ai-mode-api:/data/profile/desktop
docker compose restart
```

Prefer a bind mount instead? Swap the volume line in `docker-compose.yml` for
`./data/profile:/data/profile` and run `mkdir -p data/profile && sudo chown -R 1000:1000 data`
first — otherwise the container cannot create the profile directory and will not start.

---

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && playwright install chromium
uvicorn app.main:app --reload
```

Tests cover the pure analysis functions and need no browser:

```bash
pytest -q
```

```
app/
  main.py       FastAPI routes, auth, error mapping
  scraper.py    Drives the page, waits for streaming, extracts
  browser.py    Persistent Chromium profile per device + page pool
  js/extract.js DOM → blocks + markdown + citations
  analysis.py   Domain share, brand tracking, stats
  tasks.py      Async task queue + postback
  cache.py      TTL cache
  uule.py       Location encoding
scripts/login.py  Visible browser for preparing the profile
```

---

## Contributing

**Please open issues — that's the fastest way to keep this working.**

Google changes its markup without warning, so breakage is expected rather than exceptional.
Selector fixes ship quickly, and a good bug report is most of the work:

- **Extraction broke?** Include the query, `hl`/`gl`/`device`, and the `extracted_by` value.
  Output from `/v1/debug/html` (with `GAM_DEBUG_ENDPOINTS=true`) helps enormously.
- **Wrong or missing citations?** Paste the `citations` array and what you expected.
- **Feature ideas welcome**, particularly SEO/GEO metrics worth computing from an answer.

Pull requests are welcome for selector updates, new extractors, and language coverage.
Keep `pytest -q` green.

---

## Responsible use

This tool automates publicly visible Google search results. Google's Terms of Service
restrict automated access; how you use it is your responsibility. It contains no mechanism
for defeating verification pages and will not gain one. Query at a sane rate, for your own
research.

## License

MIT — see [LICENSE](LICENSE).
