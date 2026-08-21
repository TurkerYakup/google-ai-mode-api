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
    """
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


@pytest.fixture(scope="session")
def synthetic(extract):
    return extract(Path(__file__).parent / "fixtures" / "synthetic_ai_mode.html")


# --- her fixture icin gecerli olmasi gereken kurallar ----------------------


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
class TestAnyFixture:
    def test_extraction_succeeds(self, extract, path):
        r = extract(path)
        assert r["ok"] is True, f"ayiklama basarisiz: {r.get('reason')}"
        assert r["markdown"].strip(), "markdown bos"
        assert r["blocks"], "hic blok uretilmedi"

    def test_blocks_are_well_formed(self, extract, path):
        r = extract(path)
        allowed = {"heading", "paragraph", "list", "table", "code"}
        for b in r["blocks"]:
            assert b["type"] in allowed, f"bilinmeyen blok tipi: {b['type']}"
            if b["type"] == "list":
                assert b["items"], "bos liste blogu"
            if b["type"] == "table":
                assert b["rows"], "bos tablo blogu"

    def test_citations_are_clean(self, extract, path):
        r = extract(path)
        urls = [c["url"] for c in r["citations"]]
        assert len(urls) == len(set(urls)), "atiflarda tekrar eden URL var"
        for c in r["citations"]:
            assert c["url"].startswith("http"), f"gecersiz URL: {c['url']}"
            assert "/url?q=" not in c["url"], "Google yonlendirme linki cozulmemis"
            assert not c["domain"].endswith("google.com"), f"Google linki atif sayilmis: {c['url']}"
            assert not c["domain"].startswith("www."), f"www. soyulmamis: {c['domain']}"

    def test_follow_ups_are_questions(self, extract, path):
        r = extract(path)
        for q in r["follow_ups"]:
            assert q.endswith(("?", "？")), f"soru olmayan devam onerisi: {q}"
            assert "\n" not in q

    def test_paragraphs_are_single_line(self, extract, path):
        # Kaynak HTML'indeki girinti/satir sonlari metne sizmamali.
        for b in extract(path)["blocks"]:
            if b["type"] == "paragraph":
                assert "\n" not in b["text"], f"paragrafta ham satir sonu: {b['text'][:60]!r}"

    def test_result_is_json_serializable(self, extract, path):
        # Sonuc dogrudan API yanitina giriyor; serilestirilemeyen bir sey kalmamali.
        json.dumps(extract(path))


# --- sentetik fixture'a ozel, birebir beklentiler --------------------------


REAL = Path(__file__).parent / "fixtures" / "real_ai_mode_tr.html"


@pytest.fixture(scope="session")
def real(extract):
    return extract(REAL)


@pytest.mark.skipif(not REAL.exists(), reason="gercek fixture yok")
class TestRealFixture:
    """Gercek bir AI Mode sayfasi (tr, 'en iyi crm yazilimi'). Asil kirilgan katman bu:
    Google DOM'u degistiginde ilk burasi kirilir."""

    def test_primary_selector_still_matches_google(self, real):
        # Bu kirilirsa GAM_ANSWER_SELECTORS guncellenmeli.
        assert real["how"] == 'selector:div[data-subtree="aimc"]'

    def test_answer_has_substance(self, real):
        assert len(real["markdown"]) > 1000
        assert "Salesforce" in real["markdown"]
        assert "HubSpot" in real["markdown"]

    def test_google_ui_chrome_is_not_in_answer(self, real):
        md = real["markdown"]
        for noise in ("Herkese açık bağlantı", "Arama Sonuçları", "Geri bildirim"):
            assert noise not in md, f"Google arayuz metni cevaba sizmis: {noise}"

    def test_citations_extracted(self, real):
        domains = {c["domain"] for c in real["citations"]}
        assert len(real["citations"]) >= 5
        assert "bitrix24.com.tr" in domains

    def test_block_level_neighbours_are_separated(self, real):
        """Regression: blok komsulari ayirici olmadan birlestiriliyordu."""
        assert "TürkiyeBitrix24" not in real["markdown"]
        assert "karmaşı...Kickidler" not in real["markdown"]


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
