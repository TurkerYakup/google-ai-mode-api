"""Ham cevaptan SEO/GEO metrikleri cikarir."""

import re
from typing import Dict, List

from .models import AnswerStats, BrandMatch, Citation, DomainMatch, DomainStat


def build_citations(raw: List[Dict[str, str]]) -> List[Citation]:
    return [
        Citation(position=i, title=c.get("title") or c.get("domain", ""), url=c["url"], domain=c["domain"])
        for i, c in enumerate(raw, start=1)
    ]


def domain_stats(citations: List[Citation]) -> List[DomainStat]:
    """Domain basina atif sayisi, ilk gorunme sirasi, pay ve linkler."""
    agg: Dict[str, DomainStat] = {}
    for c in citations:
        stat = agg.get(c.domain)
        if stat is None:
            agg[c.domain] = DomainStat(
                domain=c.domain, citations=1, first_position=c.position, share=0.0, urls=[c.url]
            )
        else:
            stat.citations += 1
            stat.urls.append(c.url)

    total = len(citations) or 1
    for stat in agg.values():
        stat.share = round(stat.citations / total, 4)
    return sorted(agg.values(), key=lambda s: (-s.citations, s.first_position))


def _domain_matches(needle: str, domain: str) -> bool:
    """'ornek.com' hem ornek.com'u hem blog.ornek.com'u yakalar."""
    needle = needle.strip().lower().lstrip(".")
    needle = re.sub(r"^https?://", "", needle).split("/")[0]
    needle = needle[4:] if needle.startswith("www.") else needle
    return domain == needle or domain.endswith("." + needle)


def track_domains(citations: List[Citation], wanted: List[str]) -> List[DomainMatch]:
    out: List[DomainMatch] = []
    for w in wanted:
        hits = [c for c in citations if _domain_matches(w, c.domain)]
        out.append(
            DomainMatch(
                domain=w,
                cited=bool(hits),
                positions=[c.position for c in hits],
                urls=[c.url for c in hits],
            )
        )
    return out


def track_brands(answer: str, brands: List[str], window: int = 90) -> List[BrandMatch]:
    """Marka adinin cevap metninde gectigi yerleri, kisa baglamlariyla dondurur."""
    out: List[BrandMatch] = []
    for brand in brands:
        term = brand.strip()
        if not term:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        contexts: List[str] = []
        count = 0
        for m in pattern.finditer(answer):
            count += 1
            if len(contexts) < 5:
                start = max(0, m.start() - window)
                end = min(len(answer), m.end() + window)
                snippet = answer[start:end].replace("\n", " ").strip()
                prefix = "…" if start > 0 else ""
                suffix = "…" if end < len(answer) else ""
                contexts.append(f"{prefix}{snippet}{suffix}")
        out.append(BrandMatch(brand=brand, mentioned=count > 0, count=count, contexts=contexts))
    return out


def answer_stats(answer: str, citations: List[Citation], block_count: int = 0) -> AnswerStats:
    words = len([w for w in re.split(r"\s+", answer) if w])
    return AnswerStats(
        characters=len(answer),
        words=words,
        citation_count=len(citations),
        unique_domains=len({c.domain for c in citations}),
        block_count=block_count,
    )
