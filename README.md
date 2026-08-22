# Google AI Mode API

**Self-hosted JSON API for Google's AI Mode (`udm=50`), built for SEO / GEO research.**

[![Release](https://img.shields.io/github/v/release/TurkerYakup/google-ai-mode-api?color=success)](https://github.com/TurkerYakup/google-ai-mode-api/releases/latest)
[![CI](https://github.com/TurkerYakup/google-ai-mode-api/actions/workflows/ci.yml/badge.svg)](https://github.com/TurkerYakup/google-ai-mode-api/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Container](https://img.shields.io/badge/ghcr.io-google--ai--mode--api-2496ed?logo=docker&logoColor=white)](https://github.com/TurkerYakup/google-ai-mode-api/pkgs/container/google-ai-mode-api)

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
cp .env.example .env
```

Set a key — **the service refuses to start without one**:

```bash
sed -i "s/^GAM_API_KEY=.*/GAM_API_KEY=$(openssl rand -hex 32)/" .env
```

Then pull the prebuilt image (no build, ~2 GB with Chromium):

```bash
docker compose pull && docker compose up -d
```

Or build from source instead:

```bash
docker compose up -d --build
```

> Running on localhost only and don't want a key? Set `GAM_ALLOW_NO_AUTH=true` in `.env`.
> That is a deliberate opt-out and the service logs a warning on every start.

```bash
curl http://127.0.0.1:8000/health
```

Interactive docs (Swagger): <http://127.0.0.1:8000/docs>

> The port binds to `127.0.0.1` only. **Set `GAM_API_KEY` before** changing that in
> `docker-compose.yml`.

### Prepare the browser profile — do this before your first query

**A cold profile on a fresh IP usually gets Google's "unusual traffic" page within the
first few requests.** This is the single most common first-run experience, and it is not
a bug in this service. Handle it now rather than after a confusing `503 blocked`.

On a machine with a screen:

```bash
pip install playwright && playwright install chromium
python scripts/login.py --profile ./profile-desktop   # solve the check in the window, then close it
docker compose cp ./profile-desktop google-ai-mode-api:/data/profile/desktop
docker compose restart
```

The cookie this produces settles things down. Two things matter here:

- **Stay signed out.** Do not use your own Google account — see
  [Maintaining the browser profile](#maintaining-the-browser-profile). An IP block clears
  in hours; an account suspension does not.
- **Keep `GAM_BROWSER_CHANNEL=chromium`** (the default). Otherwise Playwright runs its
  `headless-shell` binary, which Google flags noticeably faster than the full browser.

Skipping this step works often enough that you can try a query first — just recognise
`503 blocked` for what it is when it appears.

### One query

```bash
curl -s -X POST http://127.0.0.1:8000/v1/query \
  -H 'Content-Type: application/json' \
  -d '{
        "query": "best crm software",
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

An AI Mode answer streams in a measured ~10-15 s, sometimes longer. For keyword sets or
clients that cannot wait, submit a task, get an ID, poll later — or have the result POSTed
to your webhook:

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
        "tag": "crm-cluster"
      }'
```

Tasks run **sequentially** with `GAM_BATCH_DELAY` seconds between them. That is deliberate —
firing them in parallel is the fastest way to get a verification page from Google.

---

### Use it as an LLM (OpenAI-compatible)

This is the part no SERP vendor sells: AI Mode exposed as a chat model. Point Open WebUI,
LangChain, Cursor, `openai-python` — anything that speaks the OpenAI API — at
`http://127.0.0.1:8000/v1` and it works with no shim. The model id is `google-ai-mode`,
and `GAM_API_KEY` is the API key.

```bash
curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GAM_API_KEY" \
  -d '{
        "model": "google-ai-mode",
        "messages": [{"role": "user", "content": "what is a crm"}]
      }'
```

Add `"stream": true` for server-sent events. Both `Authorization: Bearer` (what OpenAI
clients send) and `X-API-Key` are accepted.

> **Streaming is simulated.** Google delivers the whole answer before the API sees it, so
> the response is chunked after the fact rather than token-by-token as it is generated.
> Clients cannot tell the difference, but time-to-first-token is the full query latency —
> around 10–15 s, not the sub-second a real model gives you.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Status, browser pools, pending task count |
| `POST` | `/v1/query` | Single query, synchronous |
| `GET` | `/v1/query?q=…` | Single query, synchronous, convenience form |
| `POST` | `/v1/batch` | Keyword list, synchronous (use tasks for >5) |
| `POST` | **`/v1/chat/completions`** | **OpenAI-compatible chat, streaming or not — see below** |
| `GET` | **`/v1/models`** | **OpenAI-compatible model list, for clients that probe it** |
| `POST` | `/v1/tasks/query` | Queue one query → `202` + `task_id` |
| `POST` | `/v1/tasks/batch` | Queue a keyword list |
| `GET` | `/v1/tasks/{id}` | Task status and result |
| `GET` | `/v1/tasks?status=done` | List tasks |
| `DELETE` | `/v1/cache` | Flush the result cache |
| `POST` | `/v1/browser/restart` | Restart Chromium |
| `GET` | `/v1/debug/html?q=…` | Raw HTML, for fixing selectors (off by default) |
| `GET` | `/v1/debug/screenshot?q=…` | Full-page PNG, base64 |

When `GAM_API_KEY` is set, every `/v1/*` route requires the key — no exceptions — in
either an `X-API-Key` header or an `Authorization: Bearer` one. OpenAI clients send the
bearer form; both work everywhere.

### Errors

Every error — including FastAPI's own — comes back in the same shape, so you only need to
handle one:

```json
{
  "status": "error",
  "code": "blocked",
  "message": "Google routed this request to a verification page (CAPTCHA / unusual traffic).",
  "detail": "Slow down, use a different IP, or refresh the profile in a real browser."
}
```

| HTTP | `code` | What happened | What to do |
|---|---|---|---|
| `400` | `bad_request` | No non-empty `user` message in a chat request, or a batch above `GAM_MAX_BATCH_SIZE` when you set that below 50 | Fix the request |
| `401` | `unauthorized` | Missing or wrong `X-API-Key` | Send the key set in `GAM_API_KEY` |
| `404` | `not_found` | Unknown `task_id`, or debug endpoints disabled | Task results expire after `GAM_TASK_RETENTION`; for debug set `GAM_DEBUG_ENDPOINTS=true` |
| `422` | `validation_error` | Body or query parameters failed validation — empty `query`, unknown `device`, more than 50 items in a batch | `detail` carries the field-level errors |
| `500` | `internal_error` | Unexpected failure | Check `docker compose logs` |
| `502` | `no_answer` | The page loaded but no AI Mode answer was found | Google skips the AI answer for some queries. If it happens for every query, Google's DOM likely changed — see `extracted_by` and `GAM_ANSWER_SELECTORS` |
| `502` | `extract_failed` | The extraction script threw inside the page | Usually a DOM change; open an issue with the query |
| `503` | `blocked` | Google served a verification page (`/sorry/index`) | **The common one.** You hit the rate ceiling — see [Measured limits](#measured-limits). Wait, slow down, or set `GAM_PROXY_SERVER` |
| `503` | `browser_unavailable` | No free tab within the queue timeout, or the profile directory is not writable | Raise `GAM_POOL_SIZE`, or fix volume ownership — the message says which |
| `504` | `navigation_timeout` | The page did not load within `GAM_NAV_TIMEOUT` | Network or Google being slow; retry |

In batch responses each item carries its own error under `items[].error` with the same
`code` / `message`, and the batch itself still returns `200`.

---

## Request parameters

| Field | Alias | Default | Purpose |
|---|---|---|---|
| `query` | `keyword`, `q` | — | The question to ask |
| `hl` | `language_code` | `GAM_HL` | Interface language (`tr`, `en`, `de`) |
| `gl` | `country_code` | `GAM_GL` | Country code (`TR`, `US`) |
| `google_domain` | `se_domain` | `www.google.com` | e.g. `www.google.co.uk` |
| `location` | `location_name` | — | Canonical location → `uule`. **Measured to have no effect — see below** |
| `uule` | — | — | Pass your own uule; overrides `location`. Same caveat |
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

Prices below were read from each vendor's own pricing page on **22 August 2026**. They
change; check the links before you rely on them.

| Provider | AI Mode support | Price | Model |
|---|---|---|---|
| [DataForSEO](https://dataforseo.com/pricing/serp/google-ai-mode-serp-api) | Dedicated AI Mode SERP API | **$0.0012** / SERP standard queue (~5 min), **$0.0024** priority (~1 min), **$0.004** live (~6 s) | Pay as you go, [$50 minimum deposit](https://dataforseo.com/help-center/minimum-payment) (rolls over, $1 trial credit) |
| [SerpApi](https://serpapi.com/google-ai-mode-api) | `engine=google_ai_mode`; `text_blocks`, `references`, `related_questions`, `shopping_results`, `reconstructed_markdown`, `subsequent_request_token` for multi-turn | 250 searches free; **$25** / 1 000, $75 / 5 000, $275 / 30 000, up to $3 750 / 1 M. No separate AI Mode surcharge | Subscription, no pay-as-you-go |
| [Bright Data](https://brightdata.com/pricing/serp) | General SERP API — AI Mode not documented on the pricing page | **$1.50 / 1 000** PAYG; Scale $499/mo incl. 380 K then $1.30 / 1 000; 5 K/mo free | PAYG + subscription |
| [Oxylabs](https://oxylabs.io/products/scraper-api/serp/pricing) | Web Scraper API — no dedicated AI Mode product found | Google ~**$1.00 / 1 000** on the $49 Micro plan; $99 / $249 tiers; billed per successful request; 2 K free trial | Subscription tiers |
| **This project** | AI Mode only | Infrastructure cost only | Self-hosted |

### Be honest about the cost argument

At DataForSEO's standard queue, 1 000 AI Mode pages cost **$1.20**. This project's measured
ceiling is ~40 queries/hour on one residential IP — about 960/day, which you could simply
buy for roughly **$1.15/day**. So *cost is not the reason to run this.*

The reasons that do hold up:

- **AI Mode as a chat model, over the OpenAI API.** Point Open WebUI, LangChain or Cursor
  at `/v1` and Google's AI Mode becomes a model in the dropdown. **No SERP vendor sells
  this** — they return JSON for you to parse, not something you can plug into an existing
  LLM client. See [Use it as an LLM](#use-it-as-an-llm-openai-compatible).
- **`blocks[].links` maps citations to individual claims.** Vendors return a flat reference
  list; this maps which sentence cites which source.
- **GEO metrics ship built in** — domain share of voice, brand mentions with context,
  tracked domains. Elsewhere you parse the SERP and compute these yourself.
- **Your queries never leave your machine.** Relevant if you track client brands.
- **No minimum, no subscription, no per-query bill.**

**Buy instead if** you need volume, guaranteed uptime, a proxy pool, validated location
targeting, or someone to call when Google changes its markup.

---

## Measured limits

From a single residential home IP (Turkey), `GAM_POOL_SIZE=1`, full Chromium
(`GAM_BROWSER_CHANNEL=chromium`), measured 22 August 2026:

| Measurement | Value |
|---|---|
| Time per query | **~10-11 s** median (first query ~14 s) |
| Sequential queries, 5 s apart | **15/15 clean** (≈4 queries/min, 232 s) |
| Sequential queries, no gap | **28 clean, blocked on the 29th** (≈5.5/min, 311 s) |
| Combined threshold | roughly **43 queries / ~10 minutes** |
| How the block looks | `503 blocked`, instant (~1 s), `/sorry/index` |

The important detail: the block landed on request 44 **counting across both runs**. So this
behaves less like a pure rate limit and more like an accumulating budget — slowing down
delays the threshold but does not remove it. Recovery after a block can take hours.

Practical capacity: **~40 queries per hour** with pauses between clusters. Beyond that you
need a proxy (`GAM_PROXY_SERVER`).

### The healthcheck does not restart anything

`docker-compose.yml` defines a healthcheck, but `restart: unless-stopped` **does not react
to health status** — a container that goes unhealthy stays unhealthy and keeps running.
The healthcheck is a signal for you, not a self-repair mechanism.

Either watch `/health` from outside (Uptime Kuma, a cron curl, your own monitoring), or add
a supervisor that acts on it:

```yaml
  autoheal:
    image: willfarrell/autoheal
    restart: always
    environment:
      AUTOHEAL_CONTAINER_LABEL: autoheal
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

then label this service with `autoheal: "true"`. Note that most failure modes here are not
fixed by a restart — `503 blocked` means Google is refusing you, and restarting the
container will not change that.

### Memory

Measured from the container's cgroup after ~25 queries: **922 MiB in use, 1.34 GiB peak,
against a 2 GiB limit.** No OOM kill, no restart. `GAM_PAGE_RECYCLE_AFTER=25` recycles the
tab to keep this flat; `POST /v1/browser/restart` returns it to the cold baseline and is
worth calling periodically on long-running deployments.

> **Earlier releases published higher numbers here (980 MB → 1.37 GB) and they were wrong.**
> `/health` used to compute `memory_mb` by summing per-process RSS from `/proc/*/statm`.
> Chromium spawns dozens of processes that share the same library and graphics pages, and
> that sum counts every shared page once per process — so it inflated under load by roughly
> 2.5×, reporting 2325 MB while the cgroup read 922 MiB. It could show a number *above*
> `mem_limit` while the container sat at 45 % of it. Since 0.3.1 `memory_mb` reads
> `/sys/fs/cgroup/memory.current`, which counts each page once and matches `docker stats`.

---

## Known limitations

By design, and stated plainly:

- **Single IP, no proxy pool.** Query hard enough and Google shows a verification page; the
  API then returns `503 blocked`. For volume, put a residential proxy in front via
  `GAM_BROWSER_ARGS` (`--proxy-server=…`).
- **Expect to be challenged on day one.** A cold profile on an unknown IP often gets the
  "unusual traffic" page within the first few requests — normal, not a bug. This is common
  enough that handling it is a step in the quick start:
  [Prepare the browser profile](#prepare-the-browser-profile--do-this-before-your-first-query).
- **CAPTCHAs are not solved.** When a verification page appears the request fails, on
  purpose. `scripts/login.py` lets you clear it by hand in a visible browser.
- **Selectors are fragile.** Google's DOM is obfuscated and changes often. Hence three
  layers: a configurable selector list → a "largest text block" heuristic → `/v1/debug/html`
  to find a new one. The `extracted_by` field tells you which layer fired.
- **Location targeting does not work. Results follow the server's IP address.**
  This was measured, not assumed. Asking the same Turkish-language question with
  `location=Berlin,Germany` and with `location=Istanbul,Turkey` returned the same
  answer both times — and it was about restaurants in Bursa, where the test machine
  physically sits. The Berlin request cited zero `.de` domains and never mentioned
  Berlin.

  Citation-domain overlap was tried as a metric and turned out to be useless here.
  Across two runs, asking the *same* location twice gave 31 % and 43 % overlap, while
  two *different* cities gave 26 % and 8 %. With one sample per condition and that much
  spread, the number can be made to say either thing — so the verdict rests on the
  qualitative signal instead, which is binary and robust: ask for Berlin, count German
  sources. There were none.

  Two consequences. First, the `uule` encoding is the community-derived format and
  Google appears to simply ignore it on AI Mode. Second — and this is the trap —
  `resolved_location` echoes back whatever you asked for, so a response *looks* like
  the location was applied when it was not. Treat that field as "what you requested",
  never as confirmation.

  The parameters are still accepted, both so existing callers keep working and in case
  Google's behaviour changes. If you genuinely need location-specific results today,
  the only thing that works is routing the container through a proxy in that location
  (`GAM_PROXY_SERVER`). Scope of the measurement: one query, one locale, two cities,
  one IP — enough to disprove "it works", not enough to prove it never does.
- **Tasks live in memory.** A restart clears the queue. Add Redis/Postgres if you need
  durability.
- **AI Mode doesn't always trigger.** Google skips the AI answer for some queries; you get
  `502 no_answer`.
- **`answer` ends with Google's source cards.** Google places the source cards (title +
  snippet + domain) inside the same container as the answer. They are not answer prose,
  but they end up in `answer` and in `stats.words`. We tried to split them out; this DOM
  offers no reliable signal — class names are obfuscated, a card and a prose list share
  the same structure, and every `<a>` has empty text. If word count matters to your
  analysis, drop the trailing list blocks from `blocks`.
- **`follow_ups` is usually empty.** In the verified Turkish capture, AI Mode rendered no
  follow-up suggestions at all — not a single question-shaped element anywhere on the
  page. The code stays in; it may populate in other locales or layouts.

---

## Maintaining the browser profile

> ### ⚠️ Do not sign in with your own Google account
>
> **The account is a bigger risk than the IP.** This profile is then used for continuous
> automation. If you prepare it while signed in, Google ties the traffic to the **account**
> rather than the IP. An IP block clears in hours — **an account suspension does not**, and
> the appeal process is painful.
>
> Stay **signed out.** This service does not need a session; every verified measurement here
> was taken signed out. If you truly need one, use a throwaway account created for this
> purpose only — never your real one.

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
A good bug report is most of the work:

- **Extraction broke?** Include the query, `hl`/`gl`/`device`, and the `extracted_by` value.
  Output from `/v1/debug/html` (with `GAM_DEBUG_ENDPOINTS=true`) helps enormously.
- **Wrong or missing citations?** Paste the `citations` array and what you expected.
- **Feature ideas welcome**, particularly SEO/GEO metrics worth computing from an answer.

Pull requests are welcome for selector updates, new extractors, and language coverage.
Keep `pytest -q` green.

**On maintenance, plainly:** this is a side project, not a product with an SLA. It stays
maintained for as long as I use it in my own work. Selector fixes are the priority, since
without them nothing else matters; feature requests are best effort. A regression test
against a captured page — see [`tests/fixtures/`](tests/fixtures/) — is the most useful
thing you can attach to a bug report, and it is what makes a fix quick rather than a
guessing game. Always include the version from `/health`.

---

## Responsible use

This tool automates publicly visible Google search results. Google's Terms of Service
restrict automated access; how you use it is your responsibility. It contains no mechanism
for defeating verification pages and will not gain one. Query at a sane rate, for your own
research.

## License

MIT — see [LICENSE](LICENSE).
