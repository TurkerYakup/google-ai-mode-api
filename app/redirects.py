"""Google'in atif yonlendirmelerini gercek adrese cevirir.

2026-08'de Google, AI Mode atiflarini `/goto?url=<imzali blob>` seklinde vermeye
basladi. Eski `/url?q=<gercek url>` semasinda hedef adres linkin icinde duruyordu ve
extract.js sayfadan cikarabiliyordu; yeni semada blob imzali ve hedef URL sayfanin
hicbir yerinde -- ne attribute'ta ne de metinde -- bulunmuyor. Sarmali cozmenin tek
yolu Google'a sormak: GET -> 302 -> Location.

extract.js bu tur linkleri `{"domain": null, "redirect": true}` ile isaretleyip
oldugu gibi birakiyor, cozum burada yapiliyor. Cozulemeyen bir sarmal sonuctan
DUSURULUR: alan adi `google.com` olan bir atif domain istatistiklerini ve
tracked_domains eslesmelerini sessizce bozar, eksik atif ise en azindan durustur
(ve kanarya tam da bunu, 'her sorguda sifir atif'i, ariyor).
"""

import logging
from typing import Dict, Iterator, List, Optional
from urllib.parse import urljoin, urlsplit

from playwright.async_api import Error as PWError
from playwright.async_api import Page

log = logging.getLogger(__name__)

# extract.js'teki isExternal ile ayni kural.
_GOOGLE_SUFFIXES = ("google.com", "gstatic.com", "googleusercontent.com")


def domain_of(url: str) -> Optional[str]:
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def is_external(url: str) -> bool:
    domain = domain_of(url)
    return bool(domain) and not domain.endswith(_GOOGLE_SUFFIXES)


def _link_lists(data: dict) -> Iterator[List[dict]]:
    """Sonucun icindeki link listelerinin tamami: atiflar + blok ve madde linkleri."""
    citations = data.get("citations")
    if isinstance(citations, list):
        yield citations
    for block in data.get("blocks") or []:
        if isinstance(block.get("links"), list):
            yield block["links"]
        for item in block.get("items") or []:
            if isinstance(item.get("links"), list):
                yield item["links"]


def pending_urls(data: dict) -> List[str]:
    """Cozulmesi gereken benzersiz sarmal URL'ler, belgede gorunme sirasiyla."""
    out: List[str] = []
    seen = set()
    for links in _link_lists(data):
        for link in links:
            if link.get("redirect") and link["url"] not in seen:
                seen.add(link["url"])
                out.append(link["url"])
    return out


def apply(data: dict, resolved: Dict[str, str]) -> int:
    """Cozulen sarmallari yerine yazar, cozulemeyenleri duser. Dusen sayisini dondurur.

    Cozum sonrasi ayni URL'e varan iki sarmal tek atifa iner; ayrica bir sarmal zaten
    dogrudan verilmis bir linkle ayni adrese cikabilir. Tekilligi extract.js sarmal
    URL'i uzerinden saglayabiliyordu, cozulen adres uzerinden burada tekrar saglanmali.
    """
    dropped = 0
    for links in _link_lists(data):
        kept: List[dict] = []
        seen = set()
        for link in links:
            if link.pop("redirect", False):
                final = resolved.get(link["url"])
                if not final:
                    dropped += 1
                    continue
                link["url"] = final
                link["domain"] = domain_of(final)
                link["title"] = link.get("title") or link["domain"]
            if link["url"] in seen:
                continue
            seen.add(link["url"])
            kept.append(link)
        links[:] = kept
    return dropped


async def _follow(page: Page, url: str, timeout: float) -> Optional[str]:
    """Sarmalin tek adimlik hedefini dondurur, cozulemezse None.

    Once yonlendirmeyi takip ETMEDEN istiyoruz: 302'nin govdesi yok, hedef sayfayi
    indirmeye gerek kalmiyor. max_redirects=0'in davranisi Playwright surumleri
    arasinda degisebildigi icin (bazi surumler yonlendirmeyi hata sayar) hata halinde
    zincirin tamamini takip edip son adresi okuyoruz -- pahali ama dogru.
    """
    try:
        resp = await page.request.get(url, max_redirects=0, timeout=timeout * 1000)
        location = resp.headers.get("location")
        if location:
            return urljoin(url, location)
        # Yonlendirme degilmis: istegin kendisi nerede bittiyse o.
        return resp.url
    except PWError:
        pass
    try:
        resp = await page.request.get(url, timeout=timeout * 1000)
        return resp.url
    except PWError as exc:
        log.warning("Atif yonlendirmesi cozulemedi (%s): %s", url[:80], exc)
        return None


async def resolve(page: Page, urls: List[str], timeout: float) -> Dict[str, str]:
    """Sarmal -> gercek URL eslemesi. Google'a giden istek sayisi = len(urls).

    Sirayla gidiliyor, paralel degil: bu servis zaten Google'in rate-limit'ine yakin
    calisiyor ve bir sayfa icin sarmal sayisi tek haneli.
    """
    out: Dict[str, str] = {}
    for url in urls:
        final = await _follow(page, url, timeout)
        if final and is_external(final):
            out[url] = final
        elif final:
            log.info("Yonlendirme Google icinde kaldi, atif sayilmadi: %s", final[:80])
    return out
