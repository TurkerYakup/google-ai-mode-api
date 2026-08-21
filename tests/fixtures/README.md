# Ayiklama fixture'lari

`tests/test_extract.py` bu dizindeki **her** `*.html` dosyasini bulur ve `app/js/extract.js`'i
gercek Chromium icinde uzerinde calistirir. Yeni bir sayfa eklemek icin dosyayi buraya
birakmak yeterli, test kodunda degisiklik gerekmez.

## Dosyalar

| Dosya | Ne dogrular |
|---|---|
| `synthetic_ai_mode.html` | Elle yazilmis. DOM→markdown donusumunu dogrular: basliklar, ic ice listeler, tablo, `/url?q=` yonlendirme cozme, google.com linklerinin elenmesi, buton/gurultu filtresi, devam sorulari. **Google'in gercek DOM'unu temsil etmez** -- selector'larin hala tuttugunu kanitlamaz. |
| *(yok)* `real_ai_mode_*.html` | Gercek bir AI Mode sayfasi. Asil kirilgan katman budur: Google DOM'unu obfuscate ediyor ve sik degistiriyor. |

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

## Testi calistirma

```bash
pytest tests/test_extract.py -v
```

Playwright veya Chromium kurulu degilse test atlanir (`skip`), hata vermez.
Kurmak icin:

```bash
pip install playwright && playwright install chromium
```
