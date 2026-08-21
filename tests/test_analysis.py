from app.analysis import answer_stats, build_citations, domain_stats, track_brands, track_domains
from app.uule import encode_uule

RAW = [
    {"title": "A", "url": "https://blog.ornek.com/a", "domain": "blog.ornek.com"},
    {"title": "B", "url": "https://rakip.com/b", "domain": "rakip.com"},
    {"title": "C", "url": "https://ornek.com/c", "domain": "ornek.com"},
    {"title": "D", "url": "https://rakip.com/d", "domain": "rakip.com"},
]


def test_citation_positions_start_at_one():
    cits = build_citations(RAW)
    assert [c.position for c in cits] == [1, 2, 3, 4]


def test_domain_stats_sorted_by_count_then_position():
    stats = domain_stats(build_citations(RAW))
    assert stats[0].domain == "rakip.com"
    assert stats[0].citations == 2
    assert stats[0].first_position == 2
    assert stats[0].share == 0.5
    assert sum(s.citations for s in stats) == 4


def test_track_domains_matches_subdomains():
    matches = {m.domain: m for m in track_domains(build_citations(RAW), ["ornek.com", "yok.com"])}
    # blog.ornek.com ve ornek.com ikisi de sayilmali
    assert matches["ornek.com"].cited is True
    assert matches["ornek.com"].positions == [1, 3]
    assert matches["yok.com"].cited is False


def test_track_domains_accepts_url_and_www_forms():
    matches = track_domains(build_citations(RAW), ["https://www.rakip.com/x"])
    assert matches[0].cited is True
    assert matches[0].positions == [2, 4]


def test_track_brands_is_case_insensitive_with_context():
    answer = "Nike ayakkabilari populer. Ayrica NIKE kosu serisi one cikiyor."
    (match,) = track_brands(answer, ["nike"])
    assert match.mentioned is True
    assert match.count == 2
    assert "Nike" in match.contexts[0]


def test_track_brands_reports_absence():
    (match,) = track_brands("Baska bir metin", ["Adidas"])
    assert match.mentioned is False and match.count == 0


def test_answer_stats():
    stats = answer_stats("bir iki uc", build_citations(RAW), block_count=2)
    assert stats.words == 3
    assert stats.citation_count == 4
    assert stats.unique_domains == 3
    assert stats.block_count == 2


def test_uule_is_deterministic_and_prefixed():
    a = encode_uule("Istanbul,Turkey")
    assert a.startswith("w+CAIQICI")
    assert a == encode_uule("Istanbul,Turkey")
    assert a != encode_uule("Ankara,Turkey")
