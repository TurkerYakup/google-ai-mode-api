"""Google AI Mode sayfasini surer, cevabin akmasini bekler ve ayiklar."""

import asyncio
import base64
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from playwright.async_api import Error as PWError
from playwright.async_api import Page, TimeoutError as PWTimeout

from .analysis import answer_stats, build_citations, domain_stats, track_brands, track_domains
from .config import Settings
from .models import Block, QueryOptions, QueryResult
from .uule import encode_uule

log = logging.getLogger(__name__)

_EXTRACT_JS = (Path(__file__).parent / "js" / "extract.js").read_text(encoding="utf-8")

# AI Mode'a dogrudan giden arama parametresi.
_UDM_AI_MODE = "50"

_CONSENT_BUTTONS = {
    "reject": [
        "button:has-text('Reject all')",
        "button:has-text('Tümünü reddet')",
        "button:has-text('Tumunu reddet')",
        "button:has-text('Alle ablehnen')",
        "#W0wltc",
        "form[action*='consent'] button[value='reject']",
    ],
    "accept": [
        "button:has-text('Accept all')",
        "button:has-text('Tümünü kabul et')",
        "#L2AGLb",
        "form[action*='consent'] button[value='accept']",
    ],
}


class ScrapeError(RuntimeError):
    def __init__(self, code: str, message: str, detail: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


def build_url(query: str, opts: QueryOptions, s: Settings) -> tuple[str, Optional[str]]:
    """AI Mode arama URL'ini ve cozumlenen konum adini uretir."""
    params: Dict[str, str] = {
        "q": query,
        "udm": _UDM_AI_MODE,
        "hl": opts.hl or s.hl,
        "gl": opts.gl or s.gl,
    }

    resolved_location = None
    if opts.uule:
        params["uule"] = opts.uule
    elif opts.location:
        params["uule"] = encode_uule(opts.location)
        resolved_location = opts.location

    domain = opts.google_domain or s.google_domain
    return f"https://{domain}/search?{urlencode(params)}", resolved_location


async def _dismiss_consent(page: Page, s: Settings) -> None:
    """Cerez onay ekranini kapatir. Varsayilan tercih 'reject' (gizlilik dostu)."""
    if not s.auto_consent:
        return
    choice = s.consent_choice if s.consent_choice in _CONSENT_BUTTONS else "reject"
    for sel in _CONSENT_BUTTONS[choice]:
        try:
            btn = page.locator(sel).first
            if await btn.count() and await btn.is_visible():
                await btn.click(timeout=4000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                log.info("Cerez onayi kapatildi (%s)", choice)
                return
        except (PWTimeout, PWError):
            continue


async def _assert_not_blocked(page: Page) -> None:
    url = page.url
    if "/sorry/" in url or ("consent.google.com" in url and "search" not in url):
        raise ScrapeError(
            "blocked",
            "Google bu istegi dogrulama ekranina yonlendirdi (CAPTCHA / olagandisi trafik).",
            "Istek hizini dusurun, farkli bir IP kullanin veya profili tarayicida elle tazeleyin "
            "(scripts/login.py). Bu API dogrulama ekranlarini asmaya calismaz.",
        )


async def _wait_for_answer(page: Page, s: Settings, timeout: float) -> tuple[bool, str]:
    """Cevap metni akmayi bitirene kadar bekler. (truncated, son_metin) dondurur."""
    deadline = time.monotonic() + timeout
    last_text = ""
    stable_since: Optional[float] = None

    while time.monotonic() < deadline:
        try:
            text = await page.evaluate(
                "() => { const m = document.querySelector(\"div[role='main']\") || document.body;"
                " return (m.innerText || '').trim(); }"
            )
        except PWError:
            text = ""

        if text and text == last_text:
            stable_since = stable_since or time.monotonic()
            if time.monotonic() - stable_since >= s.stable_for and len(text) > 120:
                return False, text
        else:
            stable_since = None
            last_text = text

        await asyncio.sleep(s.poll_interval)

    return True, last_text


async def scrape(page: Page, query: str, opts: QueryOptions, s: Settings) -> QueryResult:
    started = time.monotonic()
    timeout = opts.timeout or s.answer_timeout
    url, resolved_location = build_url(query, opts, s)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=s.nav_timeout * 1000)
    except PWTimeout as exc:
        raise ScrapeError("navigation_timeout", f"Sayfa {s.nav_timeout}s icinde acilmadi.", str(exc)) from exc

    await _dismiss_consent(page, s)
    await _assert_not_blocked(page)

    truncated, _ = await _wait_for_answer(page, s, timeout)
    await _assert_not_blocked(page)

    try:
        data: Dict[str, Any] = await page.evaluate(
            _EXTRACT_JS, {"selectors": s.answer_selectors, "includeHtml": opts.include_html}
        )
    except PWError as exc:
        raise ScrapeError("extract_failed", "Sayfa ayiklanamadi.", str(exc)) from exc

    if not data.get("ok"):
        raise ScrapeError(
            "no_answer",
            "AI Mode cevabi bulunamadi.",
            f"reason={data.get('reason')}. Google DOM'u degismis olabilir; "
            "GAM_DEBUG_ENDPOINTS=true ile /v1/debug/html ciktisina bakip "
            "GAM_ANSWER_SELECTORS'i guncelleyin.",
        )

    answer: str = data["markdown"]
    citations = build_citations(data.get("citations") or [])
    raw_blocks = data.get("blocks") or []

    screenshot = None
    if opts.include_screenshot:
        try:
            png = await page.screenshot(full_page=True, type="png")
            screenshot = base64.b64encode(png).decode("ascii")
        except PWError as exc:
            log.warning("Ekran goruntusu alinamadi: %s", exc)

    return QueryResult(
        query=query,
        answer=answer,
        blocks=[Block(**b) for b in raw_blocks] if opts.include_blocks else None,
        citations=citations,
        domains=domain_stats(citations),
        follow_ups=(data.get("follow_ups") or []) if opts.include_follow_ups else [],
        tracked_domains=track_domains(citations, opts.track_domains),
        tracked_brands=track_brands(answer, opts.track_brands),
        stats=answer_stats(answer, citations, len(raw_blocks)),
        source_url=url,
        device=opts.device,
        hl=opts.hl or s.hl,
        gl=opts.gl or s.gl,
        resolved_location=resolved_location,
        truncated=truncated,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        extracted_by=data.get("how"),
        html=data.get("html"),
        screenshot_base64=screenshot,
    )
