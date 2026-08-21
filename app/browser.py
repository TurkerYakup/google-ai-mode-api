"""Cihaz basina kalici profilli Chromium ornekleri ve sayfa havuzlari.

Bellek notu: Chromium'un RAM'i renderer sureclerinde birikir ve uzun omurlu bir
sekmede sorgu sayisiyla birlikte buyur. Bu yuzden sekmeler havuzda sabit sayida
tutulur (her istekte yeni sekme acilmaz), her isten sonra about:blank'e dusurulur
ve N kullanimda bir kapatilip yeniden acilir -- kapanan sekme renderer surecini de
oldurur, RAM geri gelir. Havuz disinda kalan yetim sekmeler de her iadede kapatilir.
"""

import asyncio
import contextlib
import logging
import os
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

_INIT_SCRIPT = "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"

_VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 412, "height": 915},
}


class BrowserUnavailable(RuntimeError):
    pass


class _Slot:
    """Havuzdaki bir sekme ve kac istekte kullanildigi."""

    __slots__ = ("page", "uses")

    def __init__(self, page: Page) -> None:
        self.page = page
        self.uses = 0


class _DeviceContext:
    def __init__(self, ctx: BrowserContext, pages: List[Page]) -> None:
        self.ctx = ctx
        self.slots: List[_Slot] = [_Slot(p) for p in pages]
        self.pool: asyncio.Queue = asyncio.Queue()
        for s in self.slots:
            self.pool.put_nowait(s)
        self.total_uses = 0
        self.recycles = 0

    @property
    def pages(self) -> List[Page]:
        return [s.page for s in self.slots]


class BrowserSession:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._pw: Optional[Playwright] = None
        self._devices: Dict[str, _DeviceContext] = {}
        self._lock = asyncio.Lock()

    # -- yasam dongusu ------------------------------------------------------

    async def start(self) -> None:
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
            log.info("Chromium hazir: device=%s profil=%s havuz=%d", device, profile, len(dev.slots))
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

    def status(self) -> Dict[str, Dict[str, object]]:
        return {
            name: {
                "pages": len(d.slots),
                "idle": d.pool.qsize(),
                "open_tabs": len(d.ctx.pages),
                "total_uses": d.total_uses,
                "recycles": d.recycles,
            }
            for name, d in self._devices.items()
        }

    @staticmethod
    def memory_mb() -> Optional[float]:
        """Container icindeki tum sureclerin toplam RSS'i (MB). Chromium'un buyudugunu
        izlemek icin /health uzerinden gorunur; /proc yoksa None doner."""
        total = 0
        try:
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                try:
                    with open(f"/proc/{pid}/statm", "r") as fh:
                        total += int(fh.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
                except (OSError, IndexError, ValueError):
                    continue
        except OSError:
            return None
        return round(total / 1024 / 1024, 1)

    # -- kullanim -----------------------------------------------------------

    @contextlib.asynccontextmanager
    async def acquire(self, device: str = "desktop", timeout: float = 180.0) -> AsyncIterator[Page]:
        """Havuzdan bir sekme odunc al. Istek iptal olsa/patlasa da finally ile geri doner."""
        dev = await self._ensure(device)
        try:
            slot: _Slot = await asyncio.wait_for(dev.pool.get(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise BrowserUnavailable(f"'{device}' havuzunda bos sekme yok, kuyruk zaman asimina ugradi") from exc

        try:
            yield slot.page
        finally:
            await self._return(dev, slot)

    async def _return(self, dev: _DeviceContext, slot: _Slot) -> None:
        slot.uses += 1
        dev.total_uses += 1
        limit = self._s.page_recycle_after

        needs_new = slot.page.is_closed() or (limit > 0 and slot.uses >= limit)

        if needs_new:
            # Sekmeyi kapatmak renderer surecini de oldurur; biriken RAM boylece geri gelir.
            with contextlib.suppress(Exception):
                if not slot.page.is_closed():
                    await slot.page.close()
            try:
                slot.page = await dev.ctx.new_page()
                slot.uses = 0
                dev.recycles += 1
            except Exception as exc:
                # Yeni sekme acilamadi: kapali sekmeyi havuza geri koymak sonraki istegi
                # patlatirdi, o yuzden context'i komple yenilemek uzere isaretle.
                log.error("Sekme yenilenemedi (%s); tarayici yeniden baslatiliyor", exc)
                dev.pool.put_nowait(slot)
                asyncio.create_task(self.restart())
                return
        else:
            # DOM ve JS heap'i bosalt.
            with contextlib.suppress(Exception):
                await slot.page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)

        await self._close_orphans(dev)
        dev.pool.put_nowait(slot)

    async def _close_orphans(self, dev: _DeviceContext) -> None:
        """Google'in actigi popup/yeni sekmeler havuza ait degildir; birikirlerse RAM sizar."""
        known = {id(s.page) for s in dev.slots}
        for page in list(dev.ctx.pages):
            if id(page) not in known and not page.is_closed():
                with contextlib.suppress(Exception):
                    await page.close()
                log.info("Yetim sekme kapatildi")
