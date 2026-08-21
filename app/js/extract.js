// Google AI Mode sonucunu yapisal bloklara, markdown'a ve atiflara cevirir.
// Playwright'a bir ifade olarak verilir: page.evaluate(<bu dosya>, {selectors, includeHtml})
(opts) => {
  const selectors = (opts && opts.selectors) || [];
  const includeHtml = !!(opts && opts.includeHtml);

  const NOISE = [
    "script", "style", "noscript", "svg", "form", "textarea", "input",
    "g-snackbar", "[aria-hidden='true']", "[role='navigation']",
    "[role='tablist']", "[role='dialog']", "button", "[role='button']",
  ].join(",");

  const isVisible = (el) => {
    if (!el || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 20) return false;
    const st = getComputedStyle(el);
    return st.visibility !== "hidden" && st.display !== "none";
  };

  // Goreli linkleri cozmek icin taban. location.origin bazi baglamlarda (file://,
  // set_content ile yuklenen sayfa) "null" olur ve URL yapicisi taban gecersiz diye
  // ATAR -- bu da mutlak linkler dahil tum atiflarin sessizce dusmesine yol acar.
  const BASE = location.origin && location.origin !== "null" ? location.origin : "https://www.google.com";

  const unwrap = (href) => {
    try {
      const u = new URL(href, BASE);
      if (u.pathname === "/url" && u.searchParams.get("q")) return u.searchParams.get("q");
      if (u.hostname.endsWith("google.com") && u.searchParams.get("url")) return u.searchParams.get("url");
      return u.href;
    } catch (e) { return null; }
  };

  const hostOf = (href) => {
    try { return new URL(href).hostname.replace(/^www\./, ""); } catch (e) { return null; }
  };

  const isExternal = (host) =>
    host && !host.endsWith("google.com") && !host.endsWith("gstatic.com") && !host.endsWith("googleusercontent.com");

  // --- kapsayiciyi bul ---------------------------------------------------
  const findContainer = () => {
    for (const sel of selectors) {
      for (const el of document.querySelectorAll(sel)) {
        if (isVisible(el) && (el.innerText || "").trim().length > 80) return { el, how: "selector:" + sel };
      }
    }
    // Heuristik: main icindeki, cocuklarina bolunmeyen en buyuk metin blogu.
    const root = document.querySelector("div[role='main']") || document.body;
    let best = null, bestLen = 0;
    for (const el of root.querySelectorAll("div,article,section")) {
      if (!isVisible(el)) continue;
      const len = (el.innerText || "").trim().length;
      if (len < 200) continue;
      let childMax = 0;
      for (const c of el.children) childMax = Math.max(childMax, (c.innerText || "").length);
      if (childMax > len * 0.9) continue; // sadece sarmalayici
      if (len > bestLen) { bestLen = len; best = el; }
    }
    return best ? { el: best, how: "heuristic" } : null;
  };

  const found = findContainer();
  if (!found) return { ok: false, reason: "container_not_found", markdown: "", blocks: [], citations: [], follow_ups: [] };
  const root = found.el;

  // --- yardimcilar -------------------------------------------------------
  const clean = (s) => s.replace(/\u00a0/g, " ").replace(/[ \t]+/g, " ").trim();

  const inline = (node) => {
    let out = "";
    for (const n of node.childNodes) {
      // Kaynak kodundaki girinti/satir sonlari metne sizmasin; gercek satir sonu
      // yalnizca <br> ile gelir.
      if (n.nodeType === Node.TEXT_NODE) { out += n.nodeValue.replace(/\s+/g, " "); continue; }
      if (n.nodeType !== Node.ELEMENT_NODE) continue;
      if (n.matches && n.matches(NOISE)) continue;
      const tag = n.tagName.toLowerCase();
      if (tag === "br") { out += "\n"; continue; }
      const inner = inline(n);
      if (!inner.trim()) continue;
      if (tag === "strong" || tag === "b") out += "**" + inner.trim() + "**";
      else if (tag === "em" || tag === "i") out += "_" + inner.trim() + "_";
      else if (tag === "code") out += "`" + inner.trim() + "`";
      else {
        // Blok seviyesindeki komsular gorsel olarak ayri satirlar; ayirici koymazsak
        // metinleri birbirine yapisiyor ("...TurkiyeBitrix24, dunya capinda...").
        const display = getComputedStyle(n).display;
        const isBlock = display && !display.startsWith("inline") && display !== "contents";
        if (isBlock && out && !/\s$/.test(out)) out += " ";
        out += inner;
        if (isBlock) out += " ";
      }
    }
    return out;
  };

  const linksIn = (node) => {
    const seen = new Set(), out = [];
    for (const a of node.querySelectorAll("a[href]")) {
      const href = unwrap(a.getAttribute("href"));
      if (!href || !/^https?:/.test(href)) continue;
      const host = hostOf(href);
      if (!isExternal(host) || seen.has(href)) continue;
      seen.add(href);
      out.push({ title: clean(a.innerText) || clean(a.getAttribute("aria-label") || "") || host, url: href, domain: host });
    }
    return out;
  };

  // NOT: Google, cevabin altina kaynak kartlarini (baslik + snippet + domain) da
  // ayni kapsayicinin icinde liste olarak koyuyor ve bunlar 'answer' metnine
  // karisiyor. Ayirmayi denedik ancak bu DOM'da guvenilir bir sinyal yok:
  // sinif adlari obfuscated, kart ile duzyazi listesi ayni yapida, ve TUM <a>
  // elemanlarinin metni bos (gorunen metin kardes elemanlarda). Link/metin orani
  // heuristigi bu yuzden hic tetiklenmiyor. Farkli dil/sorgu fixture'lari
  // biriktikce yeniden bakilmali.
  const withoutNested = (li) => {
    const c = li.cloneNode(true);
    for (const n of c.querySelectorAll(":scope > ul, :scope > ol")) n.remove();
    return c;
  };

  // --- bloklari uret -----------------------------------------------------
  const blocks = [];

  const walk = (node, depth) => {
    for (const el of node.children) {
      if (el.matches && el.matches(NOISE)) continue;
      const tag = el.tagName.toLowerCase();

      if (/^h[1-6]$/.test(tag)) {
        const text = clean(inline(el));
        if (text) blocks.push({ type: "heading", level: Math.min(6, +tag[1] + 1), text, links: linksIn(el) });

      } else if (tag === "p") {
        const text = clean(inline(el));
        if (text) blocks.push({ type: "paragraph", text, links: linksIn(el) });

      } else if (tag === "ul" || tag === "ol") {
        // Ic ice listeler tek bir blokta, 'depth' ile toplanir. Ayri blok olarak
        // yazilsalardi alt maddeler ait olduklari ust maddeden once cikardi.
        const items = [];
        const collect = (listEl, d) => {
          for (const li of listEl.children) {
            if (li.tagName.toLowerCase() !== "li") continue;
            const nested = li.querySelector(":scope > ul, :scope > ol");
            const src = nested ? withoutNested(li) : li;
            const text = clean(inline(src));
            if (text) items.push({ text, links: linksIn(src), depth: d });
            if (nested) collect(nested, d + 1);
          }
        };
        collect(el, depth);
        if (items.length) blocks.push({ type: "list", ordered: tag === "ol", items, links: linksIn(el) });

      } else if (tag === "table") {
        const rows = [...el.querySelectorAll("tr")].map((tr) => [...tr.children].map((td) => clean(inline(td))));
        if (rows.length) blocks.push({ type: "table", rows, links: linksIn(el) });

      } else if (tag === "pre") {
        const text = el.innerText.trim();
        if (text) blocks.push({ type: "code", text, links: [] });

      } else if (el.children.length) {
        walk(el, depth);

      } else {
        const text = clean(inline(el));
        if (text) blocks.push({ type: "paragraph", text, links: linksIn(el) });
      }
    }
  };

  walk(root, 0);

  // --- markdown'a serile -------------------------------------------------
  const md = [];
  for (const b of blocks) {
    if (b.type === "heading") md.push("\n" + "#".repeat(b.level) + " " + b.text + "\n");
    else if (b.type === "paragraph") md.push(b.text + "\n");
    else if (b.type === "code") md.push("```\n" + b.text + "\n```\n");
    else if (b.type === "list") {
      // Numaralandirma her seviyede kendi sayacini kullanir; alt seviyeye inip
      // geri cikildiginda derin sayaclar sifirlanir.
      const base = b.items[0].depth || 0;
      const counters = {};
      for (const it of b.items) {
        const d = Math.max(0, (it.depth || 0) - base);
        counters[d] = (counters[d] || 0) + 1;
        for (const k of Object.keys(counters)) if (+k > d) delete counters[k];
        md.push("  ".repeat(d) + (b.ordered ? counters[d] + ". " : "- ") + it.text);
      }
      md.push("");
    } else if (b.type === "table") {
      b.rows.forEach((cells, ri) => {
        md.push("| " + cells.join(" | ") + " |");
        if (ri === 0) md.push("|" + cells.map(() => " --- ").join("|") + "|");
      });
      md.push("");
    }
  }
  const markdown = md.join("\n").replace(/\n{3,}/g, "\n\n").replace(/[ \t]+\n/g, "\n").trim();

  // --- atiflar (gorunme sirasina gore) -----------------------------------
  const citations = linksIn(root);

  // --- devam sorulari ----------------------------------------------------
  // Google bunlari cevap kapsayicisinin disinda, tiklanabilir ogeler olarak gosterir.
  const follow_ups = [];
  const fuSeen = new Set();
  const main = document.querySelector("div[role='main']") || document.body;
  for (const el of main.querySelectorAll("a,[role='button'],[role='listitem'],li,div[jsname]")) {
    if (root.contains(el)) continue;
    if (el.children.length > 2) continue;
    const t = clean(el.innerText || "");
    if (t.length < 10 || t.length > 160 || t.includes("\n")) continue;
    if (!/[?？]$/.test(t)) continue;
    if (fuSeen.has(t.toLowerCase())) continue;
    fuSeen.add(t.toLowerCase());
    follow_ups.push(t);
  }

  return {
    ok: markdown.length > 0,
    reason: markdown.length ? null : "empty_answer",
    how: found.how,
    markdown,
    blocks,
    citations,
    follow_ups: follow_ups.slice(0, 20),
    html: includeHtml ? root.innerHTML : null,
  };
}
