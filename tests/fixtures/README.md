# Ayiklama fixture'lari

`tests/test_extract.py` bu dizindeki **her** `*.html` dosyasini bulur ve `app/js/extract.js`'i
gercek Chromium icinde uzerinde calistirir. Yeni bir sayfa eklemek icin dosyayi buraya
birakmak yeterli, test kodunda degisiklik gerekmez.

## Dosyalar

| Dosya | Ne dogrular |
|---|---|
| `synthetic_ai_mode.html` | Elle yazilmis. DOM→markdown donusumunu dogrular: basliklar, ic ice listeler, tablo, `/url?q=` yonlendirme cozme, google.com linklerinin elenmesi, buton/gurultu filtresi, devam sorulari. **Google'in gercek DOM'unu temsil etmez** -- selector'larin hala tuttugunu kanitlamaz. |
| `real_ai_mode_tr.html` | Gercek sayfa, `en iyi crm yazilimi` (tr). Tam sayfa, asagidaki DevTools tarifiyle alindi. Selector'larin hala tuttugunu ve cevabin govdesindeki alti maddelik listenin bozulmadan ciktigini dogrular. |
| `real_ai_mode_tr_sources.html` | Gercek sayfa, `Bursa'da yapay zeka destekli otomasyon...` (tr). Yalnizca cevap kapsayicisi; asagiya bakin. Gizli (`display:none`) geri bildirim/yasal diyaloglarin cevaba sizmadigini dogrular ve kaynak kartlari sorununu canli tutar. |
| `real_ai_mode_goto_links.html` | Gercek sayfa, `best crm software` (2026-08-27), kanaryanin kaydettigi artifact'tan kucultuldu. Yalnizca cevap kapsayicisi. Google'in yeni atif semasini (`/goto?url=<imzali blob>`) tasir: bu sayfa duzeltmeden once sifir atif uretiyordu. |

## Atif semalari

Google, atif linklerinin bicimini 2026-08 civarinda degistirdi ve fixture'lar iki semayi
birden temsil ediyor. `extract.js` ikisini de tanimak zorunda -- hangisinin gelecegini
sayfayi gormeden bilemiyoruz:

| Sema | Ornek | Fixture |
|---|---|---|
| Eski | `/url?q=https://ornek.com/x` | `real_ai_mode_tr*.html`, `synthetic_ai_mode.html` |
| Yeni | `/goto?url=<imzali blob>` | `real_ai_mode_goto_links.html` |

Yeni semada hedef adres sayfada hicbir yerde yok; cozumu `app/redirects.py` yapiyor
(302 -> `Location`). **Eski semali fixture'lar bilerek duruyor:** Google eski bicimi
tamamen birakmis olabilir, ama bunu bilmiyoruz ve destegi dusurmenin kazanci yok --
dusurup yanilirsak bedeli yine "her sorguda sifir atif" olur. Eski semanin gercekten
oldugunu dogrulayan bir sey gorursek (ornegin aylarca hicbir canli sayfada `/url?q=`
cikmamasi) o fixture'lar tarihsel kayda dusurulebilir; o zamana kadar ikisi de canli
sozlesme.

## Gercek sayfa nasil yakalanir

Google, veri merkezi ve yogun istek gonderen IP'lere dogrulama ekrani cikarir. Sayfayi
**kendi tarayicinizdan** kaydedin -- API'ye hic istek attirmadan ayiklama katmanini
dogrulamis olursunuz.

1. Gizli sekmede AI Mode sorgusu yapin:
   `https://www.google.com/search?q=en+iyi+crm+yazilimi&udm=50&hl=tr&gl=TR`
2. Cevabin **akmasi bitene** kadar bekleyin (yarim yakalanan sayfa yaniltici test uretir).
3. DevTools konsolunda:

```js
// Script/stil/iframe'leri atar (teste gereksiz, oturum kimligi tasiyabilirler) ve
// Google'in sayfaya gomdugu API anahtarlarini temizler. Sayfada data-api="AIza..."
// gibi gercek anahtar dizileri bulunuyor; Google'in kendi public key'i olsa da
// herkese acik bir depoda durmasi secret tarayicilarini tetikler.
const d = document.documentElement.cloneNode(true);
d.querySelectorAll('script,style,link,iframe,noscript,template').forEach(e => e.remove());
d.querySelectorAll('[data-api],[data-key],[data-token]').forEach(e => {
  for (const a of ['data-api', 'data-key', 'data-token']) if (e.hasAttribute(a)) e.setAttribute(a, 'REDACTED');
});
const html = d.outerHTML.replace(/AIza[0-9A-Za-z_-]{35}/g, 'REDACTED_GOOGLE_BROWSER_KEY');
copy('<!doctype html>\n' + html);
```

> `tests/test_fixtures_clean.py` bu dizindeki her dosyayi anahtar/e-posta desenlerine
> karsi tarar. Bir sey atlarsaniz test kirilir — bilerek boyle.

4. Panoyu `tests/fixtures/real_ai_mode_tr.html` olarak kaydedin.

> **Kaydetmeden once bakin.** Oturum acikken alinan bir SERP hesap adinizi, profil
> gorselinizi veya `ei`/`sei` gibi oturum belirteclerini icerebilir. Bu dizin herkese
> acik repoda; kisisel bir sey varsa temizleyin ya da oturumu kapatip yeniden alin.

## Kucultulmus fixture'lar

`real_ai_mode_tr_sources.html` farkli bir yolla alindi: API'ye `include_html: true` ile
sorgu atildi, donen kapsayici HTML'i `<div role="main"><div data-subtree="aimc">` icine
sarildi. Sayfanin tamami degil, sadece cevap kapsayicisi var -- dolayisiyla **devam
sorulari testi bu fixture'da anlamsizdir** (`follow_ups` kapsayicinin disinda aranir).

Boyutu 400 KB'tan 31 KB'a indirmek icin ayiklamayi etkilemeyen sunlar temizlendi:
gomulu favicon'lar (`data:` URI), ikon SVG'leri, yorum icine serilestirilmis JSON
yukleri, `<script>` govdeleri ve `jsaction`/`data-ved` gibi Google ic attribute'lari.
Budamadan once ve sonra `extract.js` ayni ciktiyi uretiyor (3108 karakter) --
kucultmek testin dogruladigi seyi degistirmedi. Inline `style` attribute'lari
KORUNDU; gizli diyaloglarin `display:none` bilgisi orada.

`real_ai_mode_goto_links.html` de kucultulmus, ama kaynagi farkli: kanarya bozulmayi
yakalayinca `/v1/debug/html` ile tam sayfayi kaydetmisti (1.3 MB). Oradaki
`div[data-subtree="aimc"]` kapsayicisi kesilip `<div role="main">` icine sarildi,
sonra `<script>/<style>/<svg>` govdeleri, `data:` URI'leri, HTML yorumlari ve
`jsaction`/`data-ved`/`jsuid` gibi Google ic attribute'lari atildi: 351 KB -> 39 KB.
Atifla ilgili her sey (`href`, `aria-label`, kart yapisi) korundu.

> Artifact'tan kucultuyorsaniz **yukaridaki DevTools tarifinin redaksiyon adimlarini da
> uygulayin**: `AIza…` desenini degistirin ve `data-api`/`data-key`/`data-token`
> degerlerini `REDACTED` yapin. `<script>` govdelerini atmak cogunlukla anahtari da
> goturuyor ama buna guvenmeyin -- anahtar bir kez attribute'ta gelmisti
> (`real_ai_mode_tr.html` icindeki `data-api="REDACTED_GOOGLE_BROWSER_KEY"` o olayin
> kalintisi). `tests/test_fixtures_clean.py` son savunma hatti, ilk degil.

## Testi calistirma

```bash
pytest tests/test_extract.py -v
```

Playwright veya Chromium kurulu degilse test atlanir (`skip`), hata vermez.
Kurmak icin:

```bash
pip install playwright && playwright install chromium
```
