"""Ayiklama ile analiz arasindaki dikis: scraper.analyse() kaydedilmis sayfalar uzerinde.

test_extract.py extract.js'in ciktisini dogruluyor, test_analysis.py analiz
fonksiyonlarini elle yazilmis sozluklerle. Aradaki dikis -- Google'in sayfasindan
cikan gercek verinin analiz katmanindan gecisi -- hicbir yerde test edilmiyordu.

Kirilmasi da sessiz olur: atif objesinin bir alan adi degisse, blok semasi kaysa ya da
atif listesi bosalsa API yine 200 doner, cevap metni yine gelir, sadece sayilar yanlis
olur. Kanarya bunu gormez -- o extracted_by'a ve atif sayisina bakiyor, share of voice
hesabinin dogrulugunu bilmiyor. Urun acisindan bu, DOM kirilmasindan daha kotu bir
hata: cikti geliyor, sayi geliyor, sayi yanlis.

Google'a istek yok: sayfalar tests/fixtures/ altindan yerel olarak sunuluyor.
"""

import copy
from pathlib import Path

import pytest

from app import redirects
from app.models import QueryOptions
from app.scraper import analyse

pytest.importorskip("playwright.sync_api", reason="playwright kurulu degil")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES = sorted(FIXTURES_DIR.glob("*.html"))
REAL = FIXTURES_DIR / "real_ai_mode_tr.html"
SOURCES = FIXTURES_DIR / "real_ai_mode_tr_sources.html"
GOTO = FIXTURES_DIR / "real_ai_mode_goto_links.html"


def prepare(extract, path, resolved=None) -> dict:
    """Sayfayi ayiklar, atif sarmallarini verilen eslemeyle cozer, kopyasini dondurur.

    Kopya sart: `extract` oturum kapsamli, yani ayni sozlugu butun testler paylasiyor
    ve redirects.apply veriyi YERINDE degistiriyor. Kopyalamadan bir testin cozdugu
    sarmallar digerinin girdisini bozar.
    """
    data = copy.deepcopy(extract(path))
    redirects.apply(data, resolved or {})
    return data


# --- her fixture icin gecerli olmasi gereken kurallar ----------------------


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
class TestEveryFixture:
    def test_blocks_still_fit_the_model(self, extract, path):
        """Blok semasi kayarsa Block(**b) burada patlar, uretimde degil."""
        data = prepare(extract, path)
        parts = analyse(data, QueryOptions())
        assert parts["blocks"] is not None
        assert len(parts["blocks"]) == len(data["blocks"])
        for b in parts["blocks"]:
            assert b.text or b.items or b.rows, f"icerigi olmayan blok: {b.type}"

    def test_stats_describe_the_answer(self, extract, path):
        data = prepare(extract, path)
        parts = analyse(data, QueryOptions())
        stats = parts["stats"]
        assert stats.characters == len(parts["answer"])
        assert stats.words > 0
        assert stats.block_count == len(data["blocks"])
        assert stats.citation_count == len(parts["citations"])
        assert stats.unique_domains == len({c.domain for c in parts["citations"]})

    def test_domain_stats_add_up(self, extract, path):
        """Share of voice'un sessizce bosalmadiginin guvencesi: paylar toplami 1."""
        parts = analyse(prepare(extract, path), QueryOptions())
        cits, domains = parts["citations"], parts["domains"]
        assert sum(d.citations for d in domains) == len(cits)
        assert {d.domain for d in domains} == {c.domain for c in cits}
        for d in domains:
            mine = [c for c in cits if c.domain == d.domain]
            assert d.citations == len(mine)
            assert d.first_position == min(c.position for c in mine)
            assert d.urls == [c.url for c in mine]
        if cits:
            assert sum(d.share for d in domains) == pytest.approx(1.0, abs=0.01)
            assert domains == sorted(domains, key=lambda d: (-d.citations, d.first_position))

    def test_no_citation_reaches_analysis_without_a_domain(self, extract, path):
        """Cozulmemis bir /goto sarmali analiz katmanina hic girmemeli.

        Girerse domain None olur: track_domains icindeki domain.endswith() AttributeError
        ile patlar, Citation modeli zaten dogrulanmaz. redirects.apply bunlari dusurmek
        zorunda -- eksik atif, yanlis atiftan iyidir.
        """
        data = prepare(extract, path)
        for c in data["citations"]:
            assert c.get("domain"), f"alan adsiz atif analize giriyor: {c}"
        analyse(data, QueryOptions())  # patlamamali


# --- gercek tr sayfasi: 'en iyi crm yazilimi' ------------------------------


@pytest.mark.skipif(not REAL.exists(), reason="gercek fixture yok")
class TestRealPageAnalysis:
    def test_share_of_voice_is_not_silently_empty(self, extract):
        parts = analyse(prepare(extract, REAL), QueryOptions())
        assert len(parts["citations"]) >= 5
        assert parts["domains"], "atif var ama domain ozeti bos"
        assert parts["domains"][0].share > 0

    def test_tracked_domain_hits_match_citation_positions(self, extract):
        parts = analyse(
            prepare(extract, REAL),
            QueryOptions(track_domains=["bitrix24.com.tr", "boyle-bir-domain-yok.example"]),
        )
        hit, miss = parts["tracked_domains"]
        assert hit.cited is True and hit.positions
        assert hit.positions == [
            c.position for c in parts["citations"] if c.domain == "bitrix24.com.tr"
        ]
        assert miss.cited is False and miss.positions == []

    def test_brands_are_found_in_the_real_answer(self, extract):
        parts = analyse(
            prepare(extract, REAL),
            QueryOptions(track_brands=["Salesforce", "HubSpot", "Boyle Bir Marka Yok"]),
        )
        salesforce, hubspot, yok = parts["tracked_brands"]
        assert salesforce.mentioned and salesforce.count >= 1
        assert "Salesforce" in salesforce.contexts[0]
        assert hubspot.mentioned
        assert yok.mentioned is False and yok.count == 0

    def test_llm_mode_skips_the_seo_layer(self, extract):
        parts = analyse(
            prepare(extract, REAL),
            QueryOptions(mode="llm", track_domains=["bitrix24.com.tr"], track_brands=["Salesforce"]),
        )
        assert parts["blocks"] is None
        assert parts["domains"] == []
        assert parts["tracked_domains"] == []
        assert parts["tracked_brands"] == []
        # Kaynaklar llm modunda da donuyor (SimpleResult.sources oradan besleniyor).
        assert parts["citations"]
        assert parts["stats"].citation_count == len(parts["citations"])


@pytest.mark.skipif(not SOURCES.exists(), reason="fixture yok")
class TestSourceCardPageAnalysis:
    def test_card_domains_survive_into_the_stats(self, extract):
        """Kaynak kartlari cevap metninden cikariliyor; atif istatistiginde kalmali."""
        parts = analyse(
            prepare(extract, SOURCES),
            QueryOptions(track_domains=["kaitek.com.tr", "verodika.com", "mountaintech.plus"]),
        )
        assert all(m.cited for m in parts["tracked_domains"])
        assert {d.domain for d in parts["domains"]} >= {
            "kaitek.com.tr",
            "verodika.com",
            "mountaintech.plus",
        }


# --- /goto sarmali: analiz katmanina ne giriyor ----------------------------


@pytest.mark.skipif(not GOTO.exists(), reason="fixture yok")
class TestGotoWrappers:
    """Agustos 2026 kirilmasinin analiz tarafi.

    O gun cevap metni, bloklar ve selector saglamdi; sadece atiflar sifirlandi. Yani
    bu sayfa, 'ayiklama iyi gorunurken analiz ciktisinin bosalmasi'nin elimizdeki
    gercek ornegi.
    """

    def test_unresolved_wrappers_never_become_citations(self, extract):
        parts = analyse(prepare(extract, GOTO), QueryOptions())  # cozum eslemesi bos
        assert parts["citations"] == []
        assert parts["domains"] == []
        assert parts["stats"].citation_count == 0
        assert parts["stats"].unique_domains == 0
        # Kirilmanin dar oldugunun guvencesi: metin tarafi etkilenmiyor.
        assert len(parts["answer"]) > 1000

    def test_unresolved_wrappers_do_not_break_blocks(self, extract):
        parts = analyse(prepare(extract, GOTO), QueryOptions())
        items = [it for b in parts["blocks"] if b.type == "list" for it in (b.items or [])]
        hubspot = next(it for it in items if it["text"].startswith("**HubSpot Sales Hub:**"))
        assert hubspot["links"] == [], "cozulmemis sarmal blok linki olarak kalmis"

    def test_resolved_wrappers_produce_domain_stats(self, extract):
        pending = redirects.pending_urls(copy.deepcopy(extract(GOTO)))
        assert len(pending) == 3, "sayfada Google'in kendi saydigi 3 kaynak var"
        # Gercek hedefler imzali ve suresi geciyor. Buradaki sozlesme apply()'in
        # sozlesmesi: sarmal -> gercek adres eslemesi verildiginde analiz dogru
        # ciksin. 302'yi takip etmek redirects.resolve'un isi ve aga cikiyor.
        stand_in = {u: f"https://kaynak{i}.example/makale" for i, u in enumerate(pending, 1)}
        parts = analyse(
            prepare(extract, GOTO, stand_in),
            QueryOptions(track_domains=["kaynak2.example"]),
        )
        assert [c.domain for c in parts["citations"]] == [
            "kaynak1.example",
            "kaynak2.example",
            "kaynak3.example",
        ]
        assert parts["stats"].unique_domains == 3
        assert [d.share for d in parts["domains"]] == [pytest.approx(1 / 3, abs=1e-3)] * 3
        (match,) = parts["tracked_domains"]
        assert match.cited is True and match.positions == [2]

    def test_resolved_wrappers_reach_block_links(self, extract):
        pending = redirects.pending_urls(copy.deepcopy(extract(GOTO)))
        stand_in = {u: f"https://kaynak{i}.example/makale" for i, u in enumerate(pending, 1)}
        parts = analyse(prepare(extract, GOTO, stand_in), QueryOptions())
        items = [it for b in parts["blocks"] if b.type == "list" for it in (b.items or [])]
        hubspot = next(it for it in items if it["text"].startswith("**HubSpot Sales Hub:**"))
        assert [link["domain"] for link in hubspot["links"]] == ["kaynak1.example"]
