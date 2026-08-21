"""Tarayici profilini elle hazirlamak icin gorunur (headful) Chromium acar.

Ne zaman lazim olur:
  * Cerez onay ekrani otomatik kapanmadiysa
  * Google dogrulama ekrani ("olagandisi trafik") cikip API 503 donuyorsa
  * AI Mode'u kendi Google hesabinizla sorgulamak istiyorsaniz

Ekrani olan bir makinede calistirin (container'da ekran yok):

    python scripts/login.py --profile ./profile-desktop

Uretilen profili calisan servise aktarmak icin (profil adlandirilmis bir
Docker volume'unda tutuluyor):

    docker compose cp ./profile-desktop google-ai-mode-api:/data/profile/desktop
    docker compose exec -u root google-ai-mode-api chown -R app:app /data/profile
    docker compose restart
"""

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)


async def main() -> None:
    ap = argparse.ArgumentParser(description="AI Mode profilini elle hazirla")
    ap.add_argument("--profile", default="./profile-desktop", help="Profil dizini")
    ap.add_argument("--device", choices=["desktop", "mobile"], default="desktop")
    ap.add_argument("--url", default="https://www.google.com/search?q=test&udm=50")
    args = ap.parse_args()

    profile = Path(args.profile).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    is_mobile = args.device == "mobile"

    print(f"Profil: {profile}")
    print("Pencere aciliyor. Onaylari/oturumu hallettikten sonra pencereyi kapatin.\n")

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
            viewport={"width": 412, "height": 915} if is_mobile else {"width": 1440, "height": 900},
            is_mobile=is_mobile,
            has_touch=is_mobile,
            user_agent=MOBILE_UA if is_mobile else DESKTOP_UA,
            locale="tr-TR",
            timezone_id="Europe/Istanbul",
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(args.url)

        closed = asyncio.Event()
        ctx.on("close", lambda _: closed.set())
        await closed.wait()

    print("Profil kaydedildi. Simdi: docker compose restart")


if __name__ == "__main__":
    asyncio.run(main())
