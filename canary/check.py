#!/usr/bin/env python3
"""DOM canary for google-ai-mode-api. Stdlib only."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = os.getenv("API_BASE", "http://api:8000").rstrip("/")
API_KEY = os.getenv("GAM_API_KEY", "").strip()

QUERIES = [q.strip() for q in os.getenv(
    "CANARY_QUERIES",
    "best crm software|what is generative engine optimization|how does a heat pump work",
).split("|") if q.strip()]

# extracted_by "selector:div[data-subtree=\\"aimc\\"]" gibi doner -> PREFIX eslesmesi
OK_PREFIXES = tuple(e.strip() for e in os.getenv("CANARY_OK_EXTRACTORS", "selector:").split(",") if e.strip())

MIN_CITATIONS = int(os.getenv("CANARY_MIN_CITATIONS", "1"))
MIN_CHARS = int(os.getenv("CANARY_MIN_CHARS", "300"))

RUN_HOUR = int(os.getenv("CANARY_HOUR", "4"))
JITTER_MIN = int(os.getenv("CANARY_JITTER_MIN", "50"))
GAP_SEC = int(os.getenv("CANARY_GAP_SEC", "15"))
TIMEOUT = int(os.getenv("CANARY_TIMEOUT", "180"))

BLOCK_RETRIES = int(os.getenv("CANARY_BLOCK_RETRIES", "2"))
BLOCK_RETRY_SEC = int(os.getenv("CANARY_BLOCK_RETRY_SEC", "2700"))

DATA = pathlib.Path(os.getenv("CANARY_DATA", "/data"))
HISTORY = DATA / "history.jsonl"
STATE = DATA / "state.json"
ARTIFACTS = DATA / "artifacts"

GIST_ID = os.getenv("CANARY_GIST_ID", "").strip()
GIST_FILE = os.getenv("CANARY_GIST_FILE", "gam-status.json")
GITHUB_TOKEN = os.getenv("CANARY_GITHUB_TOKEN", "").strip()
NTFY_URL = os.getenv("CANARY_NTFY_URL", "").strip()

RUN_ONCE = os.getenv("CANARY_RUN_ONCE", "").lower() in ("1", "true", "yes")

BADGE = {
    "ok":         ("ok",         "brightgreen"),
    "fallback":   ("fallback",   "yellow"),
    "broken":     ("broken",     "red"),
    "unverified": ("unverified", "lightgrey"),
}


def log(*a):
    print(dt.datetime.now().isoformat(timespec="seconds"), *a, flush=True)


def request(method, url, body=None, headers=None, timeout=TIMEOUT):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Accept": "application/json", "User-Agent": "gam-canary/1"}
    if data:
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        code = e.code
    except Exception as e:
        return 0, {"code": "transport_error", "message": repr(e)}
    try:
        return code, json.loads(raw)
    except json.JSONDecodeError:
        return code, raw


def api_headers():
    return {"X-API-Key": API_KEY} if API_KEY else {}


ERROR_MAP = {
    "blocked":             "blocked",
    "navigation_timeout":  "network",
    "transport_error":     "network",
    "browser_unavailable": "infra",
    "no_answer":           "no_answer",
    "extract_failed":      "dom_broken",
}


def probe(query: str) -> dict:
    t0 = time.perf_counter()
    code, body = request(
        "POST", f"{API_BASE}/v1/query",
        body={"query": query, "device": "desktop", "cache": False, "include_blocks": True},
        headers=api_headers(),
    )
    ms = int((time.perf_counter() - t0) * 1000)
    out = {"query": query, "http": code, "ms": ms}

    if not isinstance(body, dict):
        out["result"] = "api_error"
        out["detail"] = str(body)[:300]
        return out

    err = body.get("code")
    if err:
        out["error_code"] = err
        out["detail"] = str(body.get("message", ""))[:200]
        out["result"] = ERROR_MAP.get(err, "api_error")
        return out

    stats = body.get("stats") or {}
    extractor = body.get("extracted_by")
    cites = stats.get("citation_count", len(body.get("citations") or []))
    chars = stats.get("characters", len(body.get("answer") or ""))
    blocks = len(body.get("blocks") or [])
    out.update({"extracted_by": extractor, "citations": cites,
                "characters": chars, "blocks": blocks})

    if chars < MIN_CHARS or cites < MIN_CITATIONS or blocks == 0:
        out["result"] = "degraded"
    elif OK_PREFIXES and extractor is not None and not str(extractor).startswith(OK_PREFIXES):
        out["result"] = "fallback"
    else:
        out["result"] = "ok"
    return out


def verdict(results):
    kinds = [r["result"] for r in results]
    if "ok" in kinds:
        return "ok"
    if "fallback" in kinds:
        return "fallback"
    if all(k in ("blocked", "network", "infra", "api_error") for k in kinds):
        return "unverified"
    return "broken"


def run_probes():
    results = []
    for attempt in range(BLOCK_RETRIES + 1):
        results = []
        for i, q in enumerate(QUERIES):
            if i:
                time.sleep(GAP_SEC)
            r = probe(q)
            log(f"  {r['result']:<10} {r['ms']:>6}ms  extracted_by={r.get('extracted_by')!r}  {q!r}")
            results.append(r)
        v = verdict(results)
        if v != "unverified" or attempt == BLOCK_RETRIES:
            return v, results
        log(f"  hepsi blocked/network -> {BLOCK_RETRY_SEC // 60} dk sonra tekrar")
        time.sleep(BLOCK_RETRY_SEC)
    return "unverified", results


def capture_html(query: str):
    url = f"{API_BASE}/v1/debug/html?" + urllib.parse.urlencode({"q": query})
    code, body = request("GET", url, headers=api_headers())
    if code != 200:
        log(f"  debug/html alinamadi ({code}) - GAM_DEBUG_ENDPOINTS=true mi?")
        return None
    html = body.get("html") if isinstance(body, dict) else body
    if not html:
        return None
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    slug = "".join(c if c.isalnum() else "-" for c in query)[:40]
    path = ARTIFACTS / f"{stamp}-{slug}.html"
    path.write_text(html, encoding="utf-8")
    log(f"  ham HTML kaydedildi: {path}")
    return str(path)


def publish(status, results):
    if not (GIST_ID and GITHUB_TOKEN):
        log("  gist ayarlanmamis, yayin atlandi")
        return
    msg, color = BADGE[status]
    today = dt.date.today().strftime("%d %b")
    payload = {
        "schemaVersion": 1,
        "label": "selectors",
        "message": f"{msg} · {today}",
        "color": color,
        "_checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "_results": [{k: r.get(k) for k in ("query", "result", "extracted_by", "citations", "ms")}
                     for r in results],
    }
    code, body = request(
        "PATCH", f"https://api.github.com/gists/{GIST_ID}",
        body={"files": {GIST_FILE: {"content": json.dumps(payload, indent=2)}}},
        headers={"Authorization": f"Bearer {GITHUB_TOKEN}",
                 "X-GitHub-Api-Version": "2022-11-28"},
        timeout=30,
    )
    log(f"  gist guncellendi ({code})" if code == 200 else f"  gist HATA {code}: {str(body)[:200]}")


def notify(title, text):
    if not NTFY_URL:
        return
    req = urllib.request.Request(
        NTFY_URL, data=text.encode(),
        headers={"Title": title, "Priority": "high", "Tags": "warning"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        log(f"  ntfy hatasi: {e!r}")


def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"status": None, "since": None, "last_alert": None}


def cycle():
    log(f"canary basliyor - {len(QUERIES)} sorgu, hedef {API_BASE}")
    status, results = run_probes()
    log(f"  => {status.upper()}")

    DATA.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with HISTORY.open("a") as f:
        f.write(json.dumps({"at": now, "status": status, "results": results}) + "\n")

    prev = load_state()
    changed = prev.get("status") != status

    if status in ("broken", "fallback") and changed:
        bad = ("no_answer", "dom_broken", "degraded", "fallback")
        q = next((r["query"] for r in results if r["result"] in bad), QUERIES[0])
        art = capture_html(q)
        notify(
            f"google-ai-mode-api: {status}",
            f"{prev.get('status')} -> {status}\n"
            + "\n".join(f"{r['result']}: {r['query']} (extracted_by={r.get('extracted_by')})"
                        for r in results)
            + (f"\nHTML: {art}" if art else ""),
        )
    elif status == "ok" and prev.get("status") in ("broken", "fallback"):
        notify("google-ai-mode-api: duzeldi", f"{prev.get('status')} -> ok")

    publish(status, results)

    STATE.write_text(json.dumps({
        "status": status,
        "since": now if changed else (prev.get("since") or now),
        "last_alert": now if changed else prev.get("last_alert"),
    }, indent=2))


def sleep_until_next_run():
    now = dt.datetime.now()
    nxt = now.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += dt.timedelta(days=1)
    secs = (nxt - now).total_seconds() + random.randint(0, JITTER_MIN * 60)
    log(f"sonraki calisma ~{secs / 3600:.1f} saat sonra")
    time.sleep(secs)


if __name__ == "__main__":
    if RUN_ONCE or "--once" in sys.argv:
        cycle()
        sys.exit(0)
    while True:
        try:
            sleep_until_next_run()
            cycle()
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"cycle patladi: {e!r}")
            time.sleep(600)
