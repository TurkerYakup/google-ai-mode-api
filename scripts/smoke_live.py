"""Canli duman testi: Google'a gercek istek atan, henuz dogrulanmamis yollari sirayla dener.

Neden ayri bir betik: pytest paketi Google'a hic istek atmaz (fixture'lar yerel sunulur).
Bu dosya tam tersini yapar -- asil servisi gercek sorgularla surer. Yaklasik 10 sorgu
harcar; olculen tavan saatte ~40 sorgu oldugu icin gunde birkac kez calistirilabilir.

Ilk 'blocked' hatasinda DURUR: engellenmis bir IP'ye istek yagdirmanin faydasi yok.

Container icinde calistirin (webhook testi 127.0.0.1'e baglaniyor):

    docker compose cp scripts/smoke_live.py google-ai-mode-api:/tmp/smoke_live.py
    docker compose exec google-ai-mode-api python /tmp/smoke_live.py

Anahtar tanimliysa:  --api-key <deger>   ya da  GAM_API_KEY ortam degiskeni
"""

import argparse
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = "http://127.0.0.1:8000"
API_KEY = None
DELAY = 5           # sorgular arasi bekleme
_used = 0           # harcanan gercek Google sorgusu


class Blocked(RuntimeError):
    pass


def call(method, path, payload=None, timeout=220, raw=False):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        body = r.read()
        return r.status, (body if raw else json.loads(body))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
        except Exception:
            err = {"code": "?", "message": body[:200]}
        if err.get("code") == "blocked":
            raise Blocked(err.get("message", "blocked"))
        return e.code, err


def spend(n=1):
    global _used
    _used += n


def poll_task(task_id, limit=240):
    """Gorev bitene kadar bekler."""
    deadline = time.time() + limit
    while time.time() < deadline:
        st, d = call("GET", f"/v1/tasks/{task_id}", timeout=30)
        if st != 200:
            return d
        if d["status"] in ("done", "error"):
            return d
        time.sleep(3)
    return {"status": "timeout"}


# --- testler ---------------------------------------------------------------


def t_llm_mode():
    """mode='llm' sade govde dondurmeli, SEO alanlari olmamali."""
    spend()
    st, d = call("POST", "/v1/query", {"query": "python nedir", "mode": "llm"})
    assert st == 200, d
    leaked = [k for k in ("blocks", "domains", "tracked_domains", "stats", "citations") if k in d]
    assert not leaked, f"SEO alanlari sizmis: {leaked}"
    assert d["answer"].strip(), "cevap bos"
    return f"{len(d['answer'])} karakter, {len(d.get('sources', []))} kaynak"


def t_mobile():
    """Mobil profil ayri context olarak acilmali ve cevap uretmeli."""
    spend()
    st, d = call("POST", "/v1/query", {"query": "en iyi telefon", "device": "mobile"})
    assert st == 200, d
    assert d["device"] == "mobile"
    st2, h = call("GET", "/health", timeout=30)
    assert "mobile" in h["browsers"], "mobil tarayici havuzu acilmadi"
    return f"{d['stats']['words']} kelime, havuz={list(h['browsers'])}"


def t_task_query():
    """Async tek gorev: 202 -> queued -> done."""
    spend()
    st, d = call("POST", "/v1/tasks/query", {"query": "crm nedir", "tag": "duman"})
    assert st == 202, d
    rec = poll_task(d["task_id"])
    assert rec["status"] == "done", rec
    assert rec["tag"] == "duman"
    return f"gorev {d['task_id'][:8]} -> {rec['result']['stats']['words']} kelime"


def t_task_batch():
    """Toplu gorev: ilerleme alani dolmali, iki sonuc donmeli."""
    spend(2)
    st, d = call("POST", "/v1/tasks/batch",
                 {"queries": ["muhasebe programi", "stok takip programi"], "tag": "duman-batch"})
    assert st == 202, d
    rec = poll_task(d["task_id"], limit=400)
    assert rec["status"] == "done", rec
    res = rec["result"]
    assert res["succeeded"] == 2, res
    return f"{res['succeeded']}/{res['count']} basarili, ilerleme={rec.get('progress')}"


def t_postback():
    """Gorev bitince postback_url'e POST gelmeli."""
    got = {}
    ready = threading.Event()

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            got.update(json.loads(self.rfile.read(n)))
            self.send_response(200)
            self.end_headers()
            ready.set()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    hook = f"http://127.0.0.1:{srv.server_address[1]}/hook"

    spend()
    st, d = call("POST", "/v1/tasks/query",
                 {"query": "seo nedir", "tag": "duman-hook", "postback_url": hook})
    assert st == 202, d
    poll_task(d["task_id"])
    assert ready.wait(30), "postback 30 sn icinde gelmedi"
    srv.shutdown()
    assert got.get("task_id") == d["task_id"], got
    return f"webhook alindi, durum={got.get('status')}, tag={got.get('tag')}"


def t_screenshot():
    """include_screenshot base64 PNG dondurmeli."""
    spend()
    st, d = call("POST", "/v1/query", {"query": "hava durumu", "include_screenshot": True})
    assert st == 200, d
    b64 = d.get("screenshot_base64")
    assert b64 and len(b64) > 5000, "ekran goruntusu yok ya da cok kucuk"
    assert base64.b64decode(b64[:64])[:4] == b"\x89PNG", "PNG imzasi yok"
    return f"{len(b64) // 1024} KB base64"


def t_stream():
    """OpenAI uyumlu SSE akisi: role parcasi, icerik parcalari, [DONE]."""
    spend()
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    req = urllib.request.Request(
        BASE + "/v1/chat/completions", method="POST", headers=headers,
        data=json.dumps({"messages": [{"role": "user", "content": "kubernetes nedir"}],
                         "stream": True}).encode())
    chunks, done = 0, False
    with urllib.request.urlopen(req, timeout=220) as r:
        for line in r:
            s = line.decode().strip()
            if not s.startswith("data:"):
                continue
            if s == "data: [DONE]":
                done = True
                break
            payload = json.loads(s[5:])
            assert payload["object"] == "chat.completion.chunk"
            chunks += 1
    assert done, "[DONE] gelmedi"
    assert chunks >= 3, f"cok az parca: {chunks}"
    return f"{chunks} parca + [DONE]"


def t_location():
    """uule gercekten sonucu degistiriyor mu? KONTROLLU olcum.

    Onceki surumu iki farkli sehri karsilastirip "farkli cikti, demek ki calisiyor"
    diyordu. Bu gecersizdi: AI Mode ayni girdiye ayni cevabi vermiyor. Olculdu --
    ayni konum iki kez sorulunca domain ortakligi %31, iki farkli sehirde %26.
    Yani teste konuma atfettirdigimiz fark, olcum gurultusunun altindaydi ve
    esik (metin birebir ayni VE ortaklik > %80) hicbir zaman saglanmadigi icin
    test gercek ne olursa olsun "etkili" diyordu.

    Dogru karsilastirma tedavi-kontrol: ayni sehir iki kez (kontrol) ve iki
    farkli sehir (tedavi). uule calisiyorsa tedavi ortakligi kontrolun belirgin
    ALTINDA olmali. Degilse fark gurultudur.
    """
    spend(4)
    q = "en iyi restoranlar"

    def ask(loc):
        st, d = call("POST", "/v1/query",
                     {"query": q, "location": loc, "hl": "tr", "gl": "TR", "cache": False})
        assert st == 200, d
        return d

    def overlap(x, y):
        a = {c["domain"] for c in x["citations"]}
        b = {c["domain"] for c in y["citations"]}
        return len(a & b) / max(1, len(a | b))

    c1 = ask("Istanbul,Turkey"); time.sleep(DELAY)
    c2 = ask("Istanbul,Turkey"); time.sleep(DELAY)
    t1 = ask("Berlin,Germany")
    control, treatment = overlap(c1, c2), overlap(c2, t1)

    # Berlin istenip Alman icerigi hic gelmiyorsa, oran hesabina gerek kalmadan bellidir.
    de = len([c for c in t1["citations"] if c["domain"].endswith(".de")])

    if treatment < control - 0.20:
        verdict = "FARKLI -> uule etkili"
    else:
        verdict = "FARK YOK -> uule etkisiz, sonuclar sunucunun IP'sine gore"
    return (f"{verdict} (kontrol %{control*100:.0f}, tedavi %{treatment*100:.0f}, "
            f"Berlin sorgusunda .de domain={de})")


TESTS = [
    ("1. llm modu (/v1/query)", t_llm_mode),
    ("2. mobil cihaz profili", t_mobile),
    ("3. async tek gorev", t_task_query),
    ("4. async toplu gorev", t_task_batch),
    ("5. postback webhook", t_postback),
    ("6. ekran goruntusu", t_screenshot),
    ("7. SSE akisi (stream)", t_stream),
    ("8. konum A/B (uule)", t_location),
]


def main():
    global API_KEY
    ap = argparse.ArgumentParser(description="Canli duman testi")
    ap.add_argument("--api-key", default=os.environ.get("GAM_API_KEY") or None)
    ap.add_argument("--only", type=int, nargs="*", help="Sadece bu numaralari calistir")
    args = ap.parse_args()
    API_KEY = args.api_key

    st, h = call("GET", "/health", timeout=20)
    print(f"servis: v{h['version']}  durum={h['status']}  RAM={h.get('memory_mb')} MB\n")

    passed = failed = 0
    for i, (name, fn) in enumerate(TESTS, 1):
        if args.only and i not in args.only:
            continue
        if i > 1:
            time.sleep(DELAY)
        try:
            print(f"{name:<28} ... ", end="", flush=True)
            print(f"GECTI  {fn()}")
            passed += 1
        except Blocked as e:
            print(f"ENGEL  {e}")
            print(f"\nGoogle engelledi. {_used} sorgu harcandi. Saatler sonra tekrar deneyin.")
            print("Kalan testler icin:  --only " + " ".join(str(n) for n in range(i, len(TESTS) + 1)))
            return
        except AssertionError as e:
            print(f"KALDI  {e}")
            failed += 1
        except Exception as e:
            print(f"HATA   {type(e).__name__}: {e}")
            failed += 1

    print(f"\nsonuc: {passed} gecti, {failed} kaldi, ~{_used} Google sorgusu harcandi")


if __name__ == "__main__":
    main()
