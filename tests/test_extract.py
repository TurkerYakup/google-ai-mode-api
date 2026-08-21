"""app/js/extract.js icin regression testleri.

Ayiklama katmani projenin en kirilgan yeri: Google DOM'u obfuscated ve sik degisiyor.
Bu testler Google'a hic istek atmadan calisir -- kaydedilmis HTML'i gercek Chromium'a
yukleyip extract.js'i uzerinde calistirir. Gercek DOM API'leri (getBoundingClientRect,
getComputedStyle) gerektigi icin jsdom degil, gercek tarayici kullaniliyor.

Yeni bir sayfa eklemek icin tests/fixtures/ altina .html birakmak yeterli; asagidaki
genel testler onu otomatik bulur.
"""

import json
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="playwright kurulu degil")

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.html"))
EXTRACT_JS = (Path(__file__).parents[1] / "app" / "js" / "extract.js").read_text(encoding="utf-8")
SELECTORS = [
    'div[data-subtree="aimc"]',
    'div[data-async-context] div[data-subtree]',
    "#im-box",
    'div[jsname="txFAF"]',
]


@pytest.fixture(scope="session")
def page():
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        except Exception as exc:  # tarayici indirilmemis olabilir
            pytest.skip(f"Chromium baslatilamadi ({exc}); `playwright install chromium` gerekiyor")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        yield ctx.new_page()
        browser.close()


FIXTURE_URL = "https://www.google.com/search?q=test&udm=50"


def extract(page, path: Path) -> dict:
    """Fixture'i gercek bir google.com URL'inde sunar ve extract.js'i uzerinde calistirir.

    set_content yerine route ile sunuyoruz: sayfanin origin'i uretimdekiyle ayni olsun,
    boylece goreli linkler (/url?q=...) ayni sekilde cozulsun. route.fulfill yaniti
    yerel uretir -- Google'a cikan bir istek YOKTUR.
    """
    html = path.read_text(encoding="utf-8")
    page.route(
        "**/*",
        lambda route: route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html),
    )
    try:
        page.goto(FIXTURE_URL, wait_until="domcontentloaded")
        return page.evaluate(EXTRACT_JS, {"selectors": SELECTORS, "includeHtml": False})
    finally:
        page.unroute("**/*")


@pytest.fixture(scope="session")
def synthetic(page):
    return extract(page, Path(__file__).parent / "fixtures" / "synthetic_ai_mode.html")


# --- her fixture icin gecerli olmasi gereken kurallar ----------------------


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
class TestAnyFixture:
    def test_extraction_succeeds(self, page, path):
        r = extract(page, path)
        assert r["ok"] is True, f"ayiklama basarisiz: {r.get('reason')}"
        assert r["markdown"].strip(), "markdown bos"
        assert r["blocks"], "hic blok uretilmedi"

    def test_blocks_are_well_formed(self, page, path):
        r = extract(page, path)
        allowed = {"heading", "paragraph", "list", "table", "code"}
        for b in r["blocks"]:
            assert b["type"] in allowed, f"bilinmeyen blok tipi: {b['type']}"
            if b["type"] == "list":
                assert b["items"], "bos liste blogu"
            if b["type"] == "table":
                assert b["rows"], "bos tablo blogu"

    def test_citations_are_clean(self, page, path):
        r = extract(page, path)
        urls = [c["url"] for c in r["citations"]]
        assert len(urls) == len(set(urls)), "atiflarda tekrar eden URL var"
        for c in r["citations"]:
            assert c["url"].startswith("http"), f"gecersiz URL: {c['url']}"
            assert "/url?q=" not in c["url"], "Google yonlendirme linki cozulmemis"
            assert not c["domain"].endswith("google.com"), f"Google linki atif sayilmis: {c['url']}"
            assert not c["domain"].startswith("www."), f"www. soyulmamis: {c['domain']}"

    def test_follow_ups_are_questions(self, page, path):
        r = extract(page, path)
        for q in r["follow_ups"]:
            assert q.endswith(("?", "？")), f"soru olmayan devam onerisi: {q}"
            assert "\n" not in q

    def test_paragraphs_are_single_line(self, page, path):
        # Kaynak HTML'indeki girinti/satir sonlari metne sizmamali.
        for b in extract(page, path)["blocks"]:
            if b["type"] == "paragraph":
                assert "\n" not in b["text"], f"paragrafta ham satir sonu: {b['text'][:60]!r}"

    def test_result_is_json_serializable(self, page, path):
        # Sonuc dogrudan API yanitina giriyor; serilestirilemeyen bir sey kalmamali.
        json.dumps(extract(page, path))


# --- sentetik fixture'a ozel, birebir beklentiler --------------------------


class TestSyntheticFixture:
    def test_container_found_by_selector_not_heuristic(self, synthetic):
        assert synthetic["how"] == 'selector:div[data-subtree="aimc"]'

    def test_noise_is_stripped(self, synthetic):
        md = synthetic["markdown"]
        assert "Geri bildirim" not in md, "buton metni ciktiya sizmis"
        assert "Bu cevabi paylas" not in md, "role=button metni ciktiya sizmis"
        assert "aria-hidden" not in md.lower(), "aria-hidden icerik ciktiya sizmis"

    def test_inline_formatting_preserved(self, synthetic):
        md = synthetic["markdown"]
        assert "**HubSpot**" in md
        assert "_Pipedrive_" in md
        assert "`Zoho CRM`" in md

    def test_google_redirect_is_unwrapped(self, synthetic):
        urls = [c["url"] for c in synthetic["citations"]]
        assert "https://ornek.org/crm-rehberi" in urls

    def test_duplicate_and_google_links_dropped(self, synthetic):
        domains = [c["domain"] for c in synthetic["citations"]]
        # Ayni URL iki kez geciyor (biri /url?q= sarmalinda), tek atif olmali.
        assert domains.count("ornek.org") == 1
        assert "support.google.com" not in domains
        assert "rakip.com" in domains

    def test_citations_keep_document_order(self, synthetic):
        # "position" alanini Python katmani (analysis.build_citations) ekliyor;
        # extract.js'in sorumlulugu belge sirasini ve tekilligi korumak.
        urls = [c["url"] for c in synthetic["citations"]]
        assert urls == list(dict.fromkeys(urls)), "sira bozulmus veya tekrar var"
        assert urls[0].startswith("https://ornek.org"), "ilk atif belgedeki ilk link olmali"

    def test_nested_bullets_follow_their_parent(self, synthetic):
        """Regression: alt maddeler ait olduklari ust maddeden ONCE yazilmamali."""
        lines = synthetic["markdown"].splitlines()
        parent = lines.index("- Ucretsiz planlar")
        child = lines.index("  - Kisitli kullanici sayisi")
        assert parent < child, "alt madde ust maddenin onune gecmis"
        assert lines[child + 1] == "  - Temel raporlama"

    def test_ordered_list_numbers_per_depth(self, synthetic):
        lines = synthetic["markdown"].splitlines()
        assert "1. Hesap olusturun" in lines
        assert "2. Verilerinizi ice aktarin" in lines
        assert "  1. CSV hazirlayin" in lines
        assert "  2. Alan eslemesi yapin" in lines
        # Alt seviyeden cikinca ust sayac kaldigi yerden devam etmeli.
        assert "3. Ekibi davet edin" in lines

    def test_table_becomes_markdown(self, synthetic):
        md = synthetic["markdown"]
        assert "| Urun | Baslangic fiyati |" in md
        assert "| HubSpot | Ucretsiz |" in md
        assert "| --- | --- |" in md

    def test_follow_ups_detected_outside_container(self, synthetic):
        fu = synthetic["follow_ups"]
        assert "CRM fiyatlari nedir?" in fu
        assert "Ucretsiz CRM secenekleri var mi?" in fu
        assert "Bu bir devam sorusu degil" not in fu

    def test_block_links_map_claims_to_sources(self, synthetic):
        """blocks[].links projenin ayirt edici ciktisi: hangi iddia hangi kaynaga dayaniyor."""
        lists = [b for b in synthetic["blocks"] if b["type"] == "list"]
        item = next(
            it for b in lists for it in b["items"] if it["text"].startswith("Kurumsal planlar")
        )
        assert [link["domain"] for link in item["links"]] == ["rakip.com"]

    def test_headings_carry_levels(self, synthetic):
        headings = [b for b in synthetic["blocks"] if b["type"] == "heading"]
        assert [h["text"] for h in headings][0] == "En iyi CRM yazilimlari"
        assert all(1 <= h["level"] <= 6 for h in headings)
