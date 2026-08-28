"""app/js/extract.js icin regression testleri.

Ayiklama katmani projenin en kirilgan yeri: Google DOM'u obfuscated ve sik degisiyor.
Bu testler Google'a hic istek atmadan calisir -- kaydedilmis HTML'i gercek Chromium'a
yukleyip extract.js'i uzerinde calistirir. Gercek DOM API'leri (getBoundingClientRect,
getComputedStyle) gerektigi icin jsdom degil, gercek tarayici kullaniliyor.

Yeni bir sayfa eklemek icin tests/fixtures/ altina .html birakmak yeterli; asagidaki
genel testler onu otomatik bulur.

Tarayiciyi acan `extract` fixture'i tests/conftest.py'de; test_pipeline.py ile ortak.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api", reason="playwright kurulu degil")

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.html"))


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
            if c.get("redirect"):
                # Imzali `/goto` sarmali: hedef adres sayfada yok, 302'yi takip edip
                # dolduran app/redirects.py. Buradaki sozlesme sadece "domain bos
                # birakildi ve isaretlendi" -- bos string veya google.com degil.
                assert c["domain"] is None, f"cozulmemis sarmalin domain'i dolu: {c}"
                continue
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

    def test_main_prose_list_survives_intact(self, real):
        """Cevabin govdesi: alti urunu tanitan madde listesi.

        Bu test bir yanlis duzeltmenin ardindan yazildi. Kaynak kartlarini ayiklamak
        icin "baglantisinin gorunur metni bos olan <li> karttir" kurali denendi ve
        bu sayfadaki duzyazi maddelerinin tamami ayni ozelligi tasidigi icin cevabin
        govdesi silindi (3491 -> 1203 karakter). Yukaridaki iki test bunu yakalamadi:
        len > 1000 hala saglaniyordu ve 'Salesforce' basliklarda geciyordu. Bir sayi
        degil, maddelerin kendisi kontrol edilmeli.
        """
        urunler = ["Salesforce", "HubSpot CRM", "Pipedrive", "Zoho CRM", "Bitrix24", "monday.com CRM"]
        items = [it["text"] for b in real["blocks"] if b["type"] == "list" for it in b["items"]]
        for urun in urunler:
            assert any(it.startswith(f"**{urun}:**") for it in items), (
                f"'{urun}' maddesi liste bloklarindan kaybolmus. Mevcut maddeler: "
                f"{[i[:40] for i in items]}"
            )

    def test_google_ui_chrome_is_not_in_answer(self, real):
        md = real["markdown"]
        for noise in (
            "Herkese açık bağlantı",
            "Arama Sonuçları",
            "Geri bildirim",
            # Bu sayfada da gizli (display:none) geri bildirim/yasal diyaloglar var
            # ve uzun sure fark edilmeden cevaba giriyorlardi; ustteki uc dize
            # onlari yakalamiyordu.
            "Gizlilik Politikamız",
            "Bu sohbetin bir kopyası",
            "yasal kaldırma talebinde",
        ):
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


# --- gizli arayuz metni + kaynak kartlari ---------------------------------


SOURCES = Path(__file__).parent / "fixtures" / "real_ai_mode_tr_sources.html"


@pytest.fixture(scope="session")
def sources(extract):
    return extract(SOURCES)


@pytest.mark.skipif(not SOURCES.exists(), reason="fixture yok")
class TestHiddenChromeAndSourceCards:
    """Gercek bir tr AI Mode sayfasi ('Bursa'da yapay zeka destekli otomasyon firmalari').

    Bu fixture iki kusuru birlikte tasidigi icin secildi; ikisi de canli kullanimda
    yakalandi, testler o yuzden var:

    1. Google, cevap kapsayicisinin icine gorunmeyen (display:none) geri bildirim ve
       yasal diyaloglari da yerlestiriyor. walk()/inline() gorunurluge hic bakmadigi
       icin bu metin cevaba giriyordu -- ekranda olmayan bir sey API cevabinda
       cikiyordu ve stats.characters/words'u sisiriyordu.
    2. Cevabin altindaki kaynak kartlari (baslik + snippet + kaynak adi) da ayni
       kapsayicida <ul> olarak duruyor ve cevap metnine karisiyordu.
    """

    def test_hidden_dialog_text_is_not_in_answer(self, sources):
        md = sources["markdown"]
        for noise in (
            "Gizlilik Politikamız",
            "Hizmet Şartlarımız",
            "Bu sohbetin bir kopyası",
            "yasal kaldırma talebinde",
            "Bizi bilgilendirdiğiniz için teşekkür",
        ):
            assert noise not in md, f"gorunmeyen arayuz metni cevaba sizmis: {noise}"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Kaynak kartlari hala cevap metnine karisiyor. Kart ile duzyazi listesi "
            "elimizdeki iki gercek sayfada yapisal olarak ayirt edilemiyor; "
            "ayrintili gerekce app/js/extract.js icinde. Bu test gecmeye baslarsa "
            "guvenilir bir sinyal bulunmus demektir: xfail'i kaldirin."
        ),
    )
    def test_source_card_snippets_are_not_in_answer(self, sources):
        md = sources["markdown"]
        for snippet in (
            "işletmenizi büyütün",          # KA Bilisim kartinin snippet'i
            "Pilot 3 ayda, ROI 6-9 ay",     # Verodika kartinin snippet'i
            "Kuruluş vizyonumuz netti",     # Kaitek kartinin snippet'i
        ):
            assert snippet not in md, f"kaynak karti metni cevaba sizmis: {snippet}"

    def test_real_answer_content_survives(self, sources):
        """Kartlari atarken duzyazi listelerini de atmadigimizin guvencesi."""
        md = sources["markdown"]
        assert len(md) > 1500
        for keep in ("Kaitek Yazılım", "MountainTech+", "Verodika", "KA Bilişim"):
            assert keep in md, f"gercek cevap icerigi kaybolmus: {keep}"

    def test_dropping_cards_does_not_drop_citations(self, sources):
        """Kartlar metinden cikiyor ama atif olarak kalmali -- linkler oradan geliyor."""
        domains = {c["domain"] for c in sources["citations"]}
        assert len(sources["citations"]) >= 8
        for d in ("kaitek.com.tr", "verodika.com", "mountaintech.plus"):
            assert d in domains, f"atif kaybolmus: {d}"

    def test_no_google_ui_links_leak_as_citations(self, sources):
        for c in sources["citations"]:
            assert "policies.google.com" not in c["url"]
            assert "support.google.com" not in c["url"]


# --- /goto sarmali (Google'in yeni atif semasi) ---------------------------


GOTO = Path(__file__).parent / "fixtures" / "real_ai_mode_goto_links.html"


@pytest.fixture(scope="session")
def goto(extract):
    return extract(GOTO)


@pytest.mark.skipif(not GOTO.exists(), reason="fixture yok")
class TestGotoRedirects:
    """Gercek bir sayfa ('best crm software', 2026-08-27), yeni atif semasiyla.

    Kanaryanin yakaladigi kirilma bu fixture'da duruyor: cevap metni, bloklar ve
    kapsayici selector'u saglamken UC sorgunun ucunde de sifir atif cikti. Sebep dar
    bir yerdeydi -- Google `/url?q=<gercek url>` yerine `/goto?url=<imzali blob>`
    vermeye basladi; linkin host'u www.google.com oldugu icin hepsi 'ic link' sanilip
    eleniyordu. Hedef adres sayfanin hicbir yerinde yok, o yuzden extract.js sarmali
    isaretleyip birakiyor ve app/redirects.py 302'yi takip ediyor.
    """

    def test_primary_selector_still_matches_google(self, goto):
        assert goto["how"] == 'selector:div[data-subtree="aimc"]'

    def test_answer_survives(self, goto):
        # Kirilmanin dar oldugunun guvencesi: metin tarafi zaten calisiyordu.
        assert len(goto["markdown"]) > 1000
        for urun in ("HubSpot Sales Hub", "Salesforce / Agentforce", "Pipedrive", "Zoho CRM"):
            assert urun in goto["markdown"]

    def test_goto_wrappers_are_kept_as_citations(self, goto):
        """Asil regression: bu sayfa duzeltmeden once sifir atif uretiyordu."""
        assert len(goto["citations"]) == 3, "sayfada Google'in kendi saydigi 3 kaynak var"
        for c in goto["citations"]:
            assert c["redirect"] is True
            assert c["domain"] is None
            assert "/goto?url=" in c["url"]
            assert c["url"].startswith("https://www.google.com/"), "sarmal mutlak URL olmali"

    def test_wrappers_reach_block_links_too(self, goto):
        """blocks[].links projenin ayirt edici ciktisi; sarmallar oraya da girmeli."""
        items = [it for b in goto["blocks"] if b["type"] == "list" for it in b["items"]]
        hubspot = next(it for it in items if it["text"].startswith("**HubSpot Sales Hub:**"))
        assert [l["redirect"] for l in hubspot["links"]] == [True]

    def test_google_ui_links_are_still_dropped(self, goto):
        """`/goto` yolunu tanimak, google.com'daki her linki atif yapmak demek degil."""
        for c in goto["citations"]:
            for ui in ("/search?", "policies.google.com", "support.google.com"):
                assert ui not in c["url"]
