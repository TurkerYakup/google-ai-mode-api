"""app/redirects.py -- Google atif sarmallarinin cozulmesi.

Ag'a cikan kisim (_follow/resolve) burada test edilmiyor; test edilen, cozum sonucunun
sonuca nasil islendigi: hangi link kaliyor, hangisi dusuyor, tekillik korunuyor mu.
Bir sarmalin google.com domain'iyle sonuca sizmasi domain istatistiklerini sessizce
bozar -- bu dosyanin asil bekcilik ettigi sey o.
"""

from app import redirects


def wrapper(url="https://www.google.com/goto?url=BLOB", title=""):
    return {"title": title, "url": url, "domain": None, "redirect": True}


def direct(url="https://ornek.org/a", domain="ornek.org", title="Ornek"):
    return {"title": title, "url": url, "domain": domain}


def result(citations=None, blocks=None):
    return {"citations": list(citations or []), "blocks": list(blocks or [])}


class TestPendingUrls:
    def test_collects_from_citations_blocks_and_items(self):
        data = result(
            citations=[wrapper("https://www.google.com/goto?url=A"), direct()],
            blocks=[
                {"type": "paragraph", "links": [wrapper("https://www.google.com/goto?url=B")]},
                {
                    "type": "list",
                    "links": [],
                    "items": [{"text": "x", "links": [wrapper("https://www.google.com/goto?url=C")]}],
                },
            ],
        )
        assert redirects.pending_urls(data) == [
            "https://www.google.com/goto?url=A",
            "https://www.google.com/goto?url=B",
            "https://www.google.com/goto?url=C",
        ]

    def test_same_wrapper_asked_once(self):
        """Ayni kaynak hem duzyazida hem kaynak kartinda geciyor; istek bir kez atilmali."""
        data = result(
            citations=[wrapper()],
            blocks=[{"type": "paragraph", "links": [wrapper()]}],
        )
        assert redirects.pending_urls(data) == ["https://www.google.com/goto?url=BLOB"]

    def test_nothing_pending_without_wrappers(self):
        assert redirects.pending_urls(result(citations=[direct()])) == []


class TestApply:
    def test_resolved_wrapper_gets_real_url_and_domain(self):
        data = result(citations=[wrapper()])
        dropped = redirects.apply(data, {"https://www.google.com/goto?url=BLOB": "https://www.g2.com/categories/crm"})
        assert dropped == 0
        assert data["citations"] == [
            {"title": "g2.com", "url": "https://www.g2.com/categories/crm", "domain": "g2.com"}
        ]

    def test_existing_title_is_kept(self):
        data = result(citations=[wrapper(title="G2 - Best CRM Software")])
        redirects.apply(data, {"https://www.google.com/goto?url=BLOB": "https://www.g2.com/x"})
        assert data["citations"][0]["title"] == "G2 - Best CRM Software"

    def test_unresolved_wrapper_is_dropped(self):
        """Sonuca google.com domain'li bir atif sizmasindansa atif hic olmasin."""
        data = result(citations=[wrapper(), direct()])
        assert redirects.apply(data, {}) == 1
        assert [c["domain"] for c in data["citations"]] == ["ornek.org"]

    def test_dropping_leaves_no_redirect_marker_behind(self):
        # 'redirect' anahtari Link modelinde yok; hicbir link uzerinde kalmamali.
        data = result(citations=[wrapper()])
        redirects.apply(data, {"https://www.google.com/goto?url=BLOB": "https://ornek.org/a"})
        assert "redirect" not in data["citations"][0]

    def test_wrappers_landing_on_same_page_collapse(self):
        """Tekillik extract.js'te sarmal URL'i uzerinden saglaniyordu; cozumden sonra
        iki farkli sarmal ayni adrese cikabilir ve atif iki kez gorunurdu."""
        data = result(citations=[wrapper(url="https://www.google.com/goto?url=A"), wrapper(url="https://www.google.com/goto?url=B")])
        redirects.apply(
            data,
            {
                "https://www.google.com/goto?url=A": "https://www.g2.com/categories/crm",
                "https://www.google.com/goto?url=B": "https://www.g2.com/categories/crm",
            },
        )
        assert len(data["citations"]) == 1

    def test_resolved_wrapper_does_not_duplicate_a_direct_link(self):
        data = result(citations=[direct(url="https://ornek.org/a"), wrapper()])
        redirects.apply(data, {"https://www.google.com/goto?url=BLOB": "https://ornek.org/a"})
        assert len(data["citations"]) == 1

    def test_block_and_item_links_are_rewritten_too(self):
        data = result(
            blocks=[
                {
                    "type": "list",
                    "links": [wrapper()],
                    "items": [{"text": "x", "links": [wrapper()]}],
                }
            ]
        )
        redirects.apply(data, {"https://www.google.com/goto?url=BLOB": "https://www.g2.com/x"})
        assert data["blocks"][0]["links"][0]["domain"] == "g2.com"
        assert data["blocks"][0]["items"][0]["links"][0]["domain"] == "g2.com"

    def test_direct_links_are_untouched(self):
        data = result(citations=[direct()])
        assert redirects.apply(data, {}) == 0
        assert data["citations"] == [direct()]


class TestIsExternal:
    def test_google_targets_are_not_citations(self):
        # Yonlendirme Google icinde kalirsa (or. bir arama sonucuna) atif degildir.
        assert not redirects.is_external("https://www.google.com/search?q=x")
        assert not redirects.is_external("https://policies.google.com/privacy")
        assert not redirects.is_external("https://lh3.googleusercontent.com/a")

    def test_real_sites_are_external(self):
        assert redirects.is_external("https://www.g2.com/categories/crm")
        assert redirects.is_external("https://www.youtube.com/watch?v=6XtgDmEtP1E")

    def test_www_is_stripped_from_domain(self):
        assert redirects.domain_of("https://www.g2.com/x") == "g2.com"
        assert redirects.domain_of("https://blog.ornek.com.tr/x") == "blog.ornek.com.tr"
