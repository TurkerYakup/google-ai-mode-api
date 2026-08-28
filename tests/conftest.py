"""Kaydedilmis sayfalar uzerinde extract.js kosturan ortak fixture.

Hem test_extract.py (ayiklama ciktisinin kendisi) hem test_pipeline.py (o ciktinin
analiz katmanindan gecisi) ayni tarayiciyi kullanir; oturum kapsamli oldugu icin
Chromium tum test kosusu boyunca bir kez acilir.
"""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXTRACT_JS = (Path(__file__).parents[1] / "app" / "js" / "extract.js").read_text(encoding="utf-8")
SELECTORS = [
    'div[data-subtree="aimc"]',
    'div[data-async-context] div[data-subtree]',
    "#im-box",
    'div[jsname="txFAF"]',
]

FIXTURE_URL = "https://www.google.com/search?q=test&udm=50"


@pytest.fixture(scope="session")
def extract():
    """Fixture'i gercek bir google.com URL'inde sunan ve extract.js'i calistiran yardimci.

    set_content yerine route ile sunuyoruz ki sayfanin origin'i uretimdekiyle ayni olsun
    ve goreli linkler (/url?q=...) ayni sekilde cozulsun. route.fulfill yaniti yerel
    uretir -- Google'a cikan bir istek YOKTUR.

    Tek bir route handler kaydedip icerigi 'holder' uzerinden degistiriyoruz. Her
    cagride yeniden route/unroute yapmak handler birikmesine ve bir fixture'in
    icerigenin digerine servis edilmesine yol aciyordu.

    Donen sozluk cagrilar arasinda PAYLASILIR ve redirects.apply() gibi yerinde
    degistiren fonksiyonlar var; degistirecekseniz once kopyalayin.
    """
    sync_api = pytest.importorskip("playwright.sync_api", reason="playwright kurulu degil")
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        except Exception as exc:  # tarayici indirilmemis olabilir
            pytest.skip(f"Chromium baslatilamadi ({exc}); `playwright install chromium` gerekiyor")

        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        holder = {"html": ""}
        page.route(
            "**/*",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html; charset=utf-8",
                # Onbelleklenirse ikinci cagride route handler hic calismaz ve
                # onceki fixture'in HTML'i servis edilir.
                headers={"cache-control": "no-store, no-cache, must-revalidate"},
                body=holder["html"],
            ),
        )
        counter = {"n": 0}

        def run(path: Path) -> dict:
            holder["html"] = Path(path).read_text(encoding="utf-8")
            counter["n"] += 1
            # URL'i de degistiriyoruz: no-store'a ek ikinci bir onbellek guvencesi.
            page.goto(f"{FIXTURE_URL}&_n={counter['n']}", wait_until="domcontentloaded")
            return page.evaluate(EXTRACT_JS, {"selectors": SELECTORS, "includeHtml": False})

        yield run
        browser.close()
