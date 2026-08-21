import asyncio
import base64
import logging
import time
from contextlib import asynccontextmanager
from typing import List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from . import __version__
from .analysis import track_brands, track_domains
from .browser import BrowserSession, BrowserUnavailable
from .cache import TTLCache
from .config import Settings, get_settings
from .models import (
    BatchItem,
    BatchRequest,
    BatchResponse,
    BatchTaskRequest,
    Device,
    ErrorResponse,
    QueryOptions,
    QueryRequest,
    QueryResult,
    TaskCreated,
    TaskInfo,
    TaskList,
    TaskRequest,
)
from .scraper import ScrapeError, build_url, scrape
from .tasks import TaskQueue, TaskRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gam")

settings: Settings = get_settings()
browser = BrowserSession(settings)
cache = TTLCache(settings.cache_ttl, settings.cache_max_entries)


# --- cekirdek is akisi -----------------------------------------------------


def _cache_key(query: str, opts: QueryOptions) -> str:
    return TTLCache.key(
        {
            "q": query.strip().lower(),
            "hl": opts.hl or settings.hl,
            "gl": opts.gl or settings.gl,
            "domain": opts.google_domain or settings.google_domain,
            "uule": opts.uule or opts.location,
            "device": opts.device,
        }
    )


async def run_query(query: str, opts: QueryOptions) -> QueryResult:
    """Onbellegi kontrol eder, gerekirse tarayiciyi surer. Onbellekten donen sonuc
    istege bagli alanlar (takip listeleri) icin yeniden hesaplanir."""
    key = _cache_key(query, opts)

    if opts.cache:
        hit: Optional[QueryResult] = cache.get(key)
        if hit is not None:
            fresh = hit.model_copy(
                update={
                    "cached": True,
                    "tracked_domains": track_domains(hit.citations, opts.track_domains),
                    "tracked_brands": track_brands(hit.answer, opts.track_brands),
                    "blocks": hit.blocks if opts.include_blocks else None,
                    "html": hit.html if opts.include_html else None,
                }
            )
            return fresh

    async with browser.acquire(opts.device) as page:
        result = await scrape(page, query, opts, settings)

    if opts.cache:
        # Ekran goruntusunu onbellekte tutma: bellegi sisirir.
        cache.set(key, result.model_copy(update={"screenshot_base64": None}))
    return result


async def run_batch(queries: List[str], opts: QueryOptions, stop_on_error: bool, on_progress=None) -> BatchResponse:
    started = time.monotonic()
    items: List[BatchItem] = []

    for i, q in enumerate(queries):
        if i > 0:
            await asyncio.sleep(settings.batch_delay)
        try:
            items.append(BatchItem(query=q, result=await run_query(q, opts)))
        except ScrapeError as exc:
            items.append(BatchItem(query=q, error={"code": exc.code, "message": exc.message}))
            if stop_on_error:
                break
        except Exception as exc:
            items.append(BatchItem(query=q, error={"code": "internal_error", "message": str(exc)}))
            if stop_on_error:
                break
        if on_progress:
            on_progress(i + 1, len(queries))

    ok = sum(1 for it in items if it.result)
    return BatchResponse(
        count=len(items),
        succeeded=ok,
        failed=len(items) - ok,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        items=items,
    )


# --- gorev kuyrugu ---------------------------------------------------------


async def _task_runner(rec: TaskRecord):
    if rec.kind == "query":
        req: TaskRequest = rec.payload
        return await run_query(req.query, req)

    req_b: BatchTaskRequest = rec.payload

    def progress(done: int, total: int) -> None:
        rec.progress = f"{done}/{total}"

    return await run_batch(req_b.queries, req_b, req_b.stop_on_error, on_progress=progress)


async def _postback(rec: TaskRecord) -> None:
    payload = rec.info().model_dump(mode="json")
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(rec.postback_url, json=payload)
    log.info("Postback gonderildi: %s -> %s", rec.id, rec.postback_url)


queue = TaskQueue(_task_runner, postback=_postback)


# --- uygulama --------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    await browser.start()
    await queue.start()
    log.info("API hazir (v%s)", __version__)
    yield
    await queue.stop()
    await browser.stop()


app = FastAPI(
    title="Google AI Mode API",
    version=__version__,
    description=(
        "Google AI Mode (udm=50) cevaplarini JSON olarak dondurur. "
        "SEO/GEO arastirmasi icin atif, domain payi, marka takibi ve konum/cihaz kirilimlari saglar."
    ),
    lifespan=lifespan,
)


async def require_key(x_api_key: Optional[str] = Header(None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Gecersiz veya eksik X-API-Key")


@app.exception_handler(ScrapeError)
async def _scrape_error_handler(_: Request, exc: ScrapeError) -> JSONResponse:
    code_map = {"blocked": 503, "navigation_timeout": 504, "no_answer": 502, "extract_failed": 502}
    return JSONResponse(
        status_code=code_map.get(exc.code, 500),
        content=ErrorResponse(code=exc.code, message=exc.message, detail=exc.detail).model_dump(),
    )


@app.exception_handler(BrowserUnavailable)
async def _browser_error_handler(_: Request, exc: BrowserUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(code="browser_unavailable", message=str(exc)).model_dump(),
    )


# --- uclar: saglik ---------------------------------------------------------


@app.get("/health", tags=["sistem"])
async def health() -> dict:
    return {
        "status": "ok" if browser.alive else "starting",
        "version": __version__,
        "browsers": browser.status(),
        "pending_tasks": queue.pending(),
        "cache_ttl": settings.cache_ttl,
    }


# --- uclar: senkron sorgu --------------------------------------------------


@app.post(
    "/v1/query",
    response_model=QueryResult,
    tags=["sorgu"],
    summary="Tek sorgu (senkron)",
    dependencies=[Depends(require_key)],
)
async def query_post(req: QueryRequest) -> QueryResult:
    return await run_query(req.query, req)


@app.get(
    "/v1/query",
    response_model=QueryResult,
    tags=["sorgu"],
    summary="Tek sorgu (senkron, GET)",
    dependencies=[Depends(require_key)],
)
async def query_get(
    q: str = Query(..., min_length=1, max_length=2000, description="Sorgu metni"),
    hl: Optional[str] = None,
    gl: Optional[str] = None,
    location: Optional[str] = None,
    device: Device = "desktop",
    track_domains: Optional[str] = Query(None, description="Virgulle ayrilmis domain listesi"),
    track_brands: Optional[str] = Query(None, description="Virgulle ayrilmis marka listesi"),
    include_blocks: bool = True,
    include_html: bool = False,
    include_screenshot: bool = False,
    cache_: bool = Query(True, alias="cache"),
    timeout: Optional[float] = Query(None, ge=5, le=300),
) -> QueryResult:
    opts = QueryOptions(
        hl=hl,
        gl=gl,
        location=location,
        device=device,
        track_domains=[d.strip() for d in (track_domains or "").split(",") if d.strip()],
        track_brands=[b.strip() for b in (track_brands or "").split(",") if b.strip()],
        include_blocks=include_blocks,
        include_html=include_html,
        include_screenshot=include_screenshot,
        cache=cache_,
        timeout=timeout,
    )
    return await run_query(q, opts)


@app.post(
    "/v1/batch",
    response_model=BatchResponse,
    tags=["sorgu"],
    summary="Coklu keyword (senkron, sirayla)",
    description="Uzun surer; 5'ten fazla keyword icin /v1/tasks/batch tercih edin.",
    dependencies=[Depends(require_key)],
)
async def batch_post(req: BatchRequest) -> BatchResponse:
    if len(req.queries) > settings.max_batch_size:
        raise HTTPException(400, f"En fazla {settings.max_batch_size} sorgu")
    return await run_batch(req.queries, req, req.stop_on_error)


# --- uclar: async gorevler -------------------------------------------------


def _created(rec: TaskRecord) -> TaskCreated:
    return TaskCreated(task_id=rec.id, status=rec.status, tag=rec.tag, created_at=rec.created_at,
                       poll_url=f"/v1/tasks/{rec.id}")


@app.post(
    "/v1/tasks/query",
    response_model=TaskCreated,
    status_code=202,
    tags=["gorev"],
    summary="Tek sorguyu kuyruga at",
    dependencies=[Depends(require_key)],
)
async def task_query(req: TaskRequest) -> TaskCreated:
    return _created(queue.submit("query", req, req.tag, req.postback_url))


@app.post(
    "/v1/tasks/batch",
    response_model=TaskCreated,
    status_code=202,
    tags=["gorev"],
    summary="Keyword listesini kuyruga at",
    dependencies=[Depends(require_key)],
)
async def task_batch(req: BatchTaskRequest) -> TaskCreated:
    if len(req.queries) > settings.max_batch_size:
        raise HTTPException(400, f"En fazla {settings.max_batch_size} sorgu")
    return _created(queue.submit("batch", req, req.tag, req.postback_url))


@app.get("/v1/tasks", response_model=TaskList, tags=["gorev"], dependencies=[Depends(require_key)])
async def task_list(
    status: Optional[str] = Query(None, pattern="^(queued|running|done|error)$"),
    limit: int = Query(50, ge=1, le=200),
) -> TaskList:
    recs = queue.list(status, limit)
    return TaskList(count=len(recs), tasks=[r.info(include_result=False) for r in recs])


@app.get("/v1/tasks/{task_id}", response_model=TaskInfo, tags=["gorev"], dependencies=[Depends(require_key)])
async def task_get(task_id: str) -> TaskInfo:
    rec = queue.get(task_id)
    if rec is None:
        raise HTTPException(404, "Gorev bulunamadi")
    return rec.info()


# --- uclar: bakim ----------------------------------------------------------


@app.delete("/v1/cache", tags=["sistem"], dependencies=[Depends(require_key)])
async def cache_clear() -> dict:
    return {"cleared": cache.clear()}


@app.post("/v1/browser/restart", tags=["sistem"], dependencies=[Depends(require_key)])
async def browser_restart() -> dict:
    await browser.restart()
    return {"status": "ok", "browsers": browser.status()}


# --- uclar: hata ayiklama --------------------------------------------------


def _require_debug() -> None:
    if not settings.debug_endpoints:
        raise HTTPException(404, "Debug uclari kapali (GAM_DEBUG_ENDPOINTS=true ile acin)")


@app.get("/v1/debug/html", response_class=PlainTextResponse, tags=["debug"], dependencies=[Depends(require_key)])
async def debug_html(q: str, device: Device = "desktop") -> str:
    """Google DOM'u degistiginde yeni selector bulmak icin sayfanin ham HTML'i."""
    _require_debug()
    opts = QueryOptions(device=device, cache=False)
    url, _ = build_url(q, opts, settings)
    async with browser.acquire(device) as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=settings.nav_timeout * 1000)
        await asyncio.sleep(6)
        return await page.content()


@app.get("/v1/debug/screenshot", tags=["debug"], dependencies=[Depends(require_key)])
async def debug_screenshot(q: str, device: Device = "desktop") -> dict:
    _require_debug()
    opts = QueryOptions(device=device, cache=False)
    url, _ = build_url(q, opts, settings)
    async with browser.acquire(device) as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=settings.nav_timeout * 1000)
        await asyncio.sleep(6)
        png = await page.screenshot(full_page=True, type="png")
    return {"url": url, "screenshot_base64": base64.b64encode(png).decode("ascii")}
