"""Cihaz basina kalici profilli Chromium ornekleri ve sayfa havuzlari."""

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from .config import Settings

log = logging.getLogger(__name__)

BASE_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-blink-features=AutomationControlled",
]

# Playwright'in biraktigi navigator.webdriver bayragini gizler; Chromium'un
# otomasyon banner'ini kapatmakla ayni amac.
_INIT_SCRIPT = "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"

_VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 412, "height": 915},
}


class BrowserUnavailable(RuntimeError):
    pass


class _DeviceContext:
    def __init__(self, ctx: BrowserContext, pages: List[Page]) -> None:
        self.ctx = ctx
        self.pages = pages
        self.pool: asyncio.Queue[Page] = asyncio.Queue()
        for p in pages:
            self.pool.put_nowait(p)


class BrowserSession:
    """Cihaz basina tek bir persistent context; es zamanlilik sayfa havuzuyla sinirli."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._pw: Optional[Playwright] = None
        self._devices: Dict[str, _DeviceContext] = {}
        self._lock = asyncio.Lock()

    # -- yasam dongusu ------------------------------------------------------

    async def start(self) -> None:
        """Playwright'i baslat ve varsayilan (desktop) profili acar. Mobil profil ilk istekte acilir."""
        async with self._lock:
            if self._pw is None:
                self._pw = await async_playwright().start()
        await self._ensure("desktop")

    async def _ensure(self, device: str) -> _DeviceContext:
        if device in self._devices:
            return self._devices[device]

        async with self._lock:
            if device in self._devices:
                return self._devices[device]
            if self._pw is None:
                self._pw = await async_playwright().start()

            s = self._s
            profile = Path(s.profile_dir) / device
            profile.mkdir(parents=True, exist_ok=True)
            is_mobile = device == "mobile"

            ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=s.headless,
                args=BASE_ARGS + list(s.browser_args),
                viewport=_VIEWPORTS[device],
                device_scale_factor=3 if is_mobile else 1,
                is_mobile=is_mobile,
                has_touch=is_mobile,
                locale=s.locale,
                timezone_id=s.timezone,
                user_agent=s.mobile_user_agent if is_mobile else s.user_agent,
            )
            await ctx.add_init_script(_INIT_SCRIPT)
            ctx.set_default_timeout(s.nav_timeout * 1000)

            pages = list(ctx.pages)  # persistent context bir sayfayla acilir
            while len(pages) < max(1, s.pool_size):
                pages.append(await ctx.new_page())

            dev = _DeviceContext(ctx, pages[: max(1, s.pool_size)])
            self._devices[device] = dev
            log.info("Chromium hazir: device=%s profil=%s havuz=%d", device, profile, len(dev.pages))
            return dev

    async def stop(self) -> None:
        async with self._lock:
            for dev in self._devices.values():
                with contextlib.suppress(Exception):
                    await dev.ctx.close()
            self._devices.clear()
            with contextlib.suppress(Exception):
                if self._pw:
                    await self._pw.stop()
            self._pw = None

    async def restart(self) -> None:
        log.warning("Tarayici yeniden baslatiliyor")
        await self.stop()
        await self.start()

    @property
    def alive(self) -> bool:
        return bool(self._devices)

    def status(self) -> Dict[str, Dict[str, int]]:
        return {
            name: {"pages": len(d.pages), "idle": d.pool.qsize()}
            for name, d in self._devices.items()
        }

    # -- kullanim -----------------------------------------------------------

    @contextlib.asynccontextmanager
    async def acquire(self, device: str = "desktop", timeout: float = 180.0) -> AsyncIterator[Page]:
        """Havuzdan bir sayfa odunc al; is bitince temizleyip geri koyar."""
        dev = await self._ensure(device)
        try:
            page = await asyncio.wait_for(dev.pool.get(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise BrowserUnavailable(f"'{device}' havuzunda bos sayfa yok, kuyruk zaman asimina ugradi") from exc

        try:
            yield page
        finally:
            await self._return(dev, page)

    async def _return(self, dev: _DeviceContext, page: Page) -> None:
        if page.is_closed():
            with contextlib.suppress(Exception):
                page = await dev.ctx.new_page()
        # Sekmeyi bosalt ki sonraki istek onceki sonucu okumasin.
        with contextlib.suppress(Exception):
            await page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
        dev.pool.put_nowait(page)
