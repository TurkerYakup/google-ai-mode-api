# Google AI Mode API

**Google AI Mode (`udm=50`) cevaplarını JSON döndüren, kendi sunucunuzda çalışan API.
SEO / GEO araştırması için.**

🇬🇧 [English README](README.md)

Google'ın resmî bir AI Mode API'si yok. Bu servis, Docker içinde headless Chromium
(Playwright) ile AI Mode sonuç sayfasını açar, cevabın akması bitene kadar bekler ve
yapılandırılmış JSON döndürür.

Klasik sıralama takibinin cevaplayamadığı tek bir soru etrafında kuruldu:

> **Google bu sorguya yapay zekâyla cevap verirken kimin içeriğine atıf yapıyor — ve o biz miyiz?**

---

## Ne döndürür

```jsonc
{
  "status": "ok",
  "query": "en iyi crm yazılımı",
  "answer": "## Öne çıkan seçenekler\n- **HubSpot** …",   // markdown
  "blocks": [                                              // iddia bazında yapısal parçalar
    { "type": "paragraph", "text": "…", "links": [ { "url": "…", "domain": "hubspot.com" } ] }
  ],
  "citations": [                                           // görünme sırasına göre
    { "position": 1, "title": "…", "url": "https://…", "domain": "hubspot.com" }
  ],
  "domains": [                                             // domain başına atıf payı
    { "domain": "hubspot.com", "citations": 3, "first_position": 1, "share": 0.375, "urls": ["…"] }
  ],
  "follow_ups": ["CRM fiyatları nedir?"],                  // Google'ın önerdiği devam soruları
  "tracked_domains": [ { "domain": "siteniz.com", "cited": true, "positions": [2] } ],
  "tracked_brands": [ { "brand": "Markanız", "mentioned": true, "count": 2, "contexts": ["…"] } ],
  "stats": { "characters": 1840, "words": 260, "citation_count": 8, "unique_domains": 5, "block_count": 12 },
  "source_url": "https://www.google.com/search?q=…&udm=50",
  "device": "desktop", "hl": "tr", "gl": "TR",
  "resolved_location": "Istanbul,Turkey",
  "cached": false, "truncated": false, "elapsed_ms": 24310
}
```

En kıymetli kısım `blocks[].links`: tüm cevap için tek bir düz link listesi vermek yerine,
**hangi cümlenin hangi kaynağa dayandığını** eşleştirir.

---

## Hızlı başlangıç

```bash
git clone https://github.com/TurkerYakup/ai-mode-api.git
cd ai-mode-api
cp .env.example .env          # localhost dışına açacaksanız GAM_API_KEY doldurun
docker compose up -d --build
```

```bash
curl http://127.0.0.1:8000/health
```

Swagger arayüzü: <http://127.0.0.1:8000/docs>

> Port yalnızca `127.0.0.1`'e bağlıdır. `docker-compose.yml` içindeki bu satırı
> değiştirmeden **önce `GAM_API_KEY` verin**.

### Tek sorgu

```bash
curl -s -X POST http://127.0.0.1:8000/v1/query \
  -H 'Content-Type: application/json' \
  -d '{
        "query": "Bursa yapay zeka firmaları",
        "location": "Bursa,Turkey",
        "device": "desktop",
        "track_domains": ["siteniz.com", "rakip.com"],
        "track_brands": ["Markanız"]
      }'
```

Hızlı deneme için GET:

```bash
curl "http://127.0.0.1:8000/v1/query?q=en+iyi+crm&track_domains=siteniz.com,rakip.com"
```

### Async görev (önerilen)

AI Mode cevabı 30–90 sn akar; çoğu HTTP istemcisi bu kadar beklemez. Görev aç, ID al,
sonra sonucu çek — ya da bitince webhook'unuza POST edilsin:

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tasks/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"crm karşılaştırma","tag":"haftalik-tarama","postback_url":"https://sisteminiz/webhook"}'
# → {"task_id":"a1b2…","status":"queued","poll_url":"/v1/tasks/a1b2…"}

curl -s http://127.0.0.1:8000/v1/tasks/a1b2…
```

### Keyword listesi

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tasks/batch \
  -H 'Content-Type: application/json' \
  -d '{
        "queries": ["crm yazılımı", "crm fiyatları", "ücretsiz crm"],
        "track_domains": ["siteniz.com"],
        "location": "Ankara,Turkey",
        "tag": "crm-kumesi"
      }'
```

Görevler **sırayla**, aralarında `GAM_BATCH_DELAY` saniye bekleyerek işlenir. Bu kasıtlı:
paralel gitmek Google'ın doğrulama ekranını çağırmanın en hızlı yoludur.

---

## Uçlar

| Method | Yol | Açıklama |
|---|---|---|
| `GET` | `/health` | Durum, tarayıcı havuzları, bekleyen görev sayısı |
| `POST` | `/v1/query` | Tek sorgu, senkron |
| `GET` | `/v1/query?q=…` | Tek sorgu, senkron, pratik biçim |
| `POST` | `/v1/batch` | Keyword listesi, senkron (5'ten fazlası için görev kullanın) |
| `POST` | `/v1/tasks/query` | Tek sorguyu kuyruğa atar → `202` + `task_id` |
| `POST` | `/v1/tasks/batch` | Keyword listesini kuyruğa atar |
| `GET` | `/v1/tasks/{id}` | Görev durumu ve sonucu |
| `GET` | `/v1/tasks?status=done` | Görev listesi |
| `DELETE` | `/v1/cache` | Önbelleği temizler |
| `POST` | `/v1/browser/restart` | Chromium'u yeniden başlatır |
| `GET` | `/v1/debug/html?q=…` | Ham HTML, selector düzeltmek için (kapalı gelir) |
| `GET` | `/v1/debug/screenshot?q=…` | Tam sayfa PNG, base64 |

`GAM_API_KEY` doluysa tüm `/v1/*` uçları `X-API-Key` başlığı ister.

---

## İstek parametreleri

| Alan | Alias | Varsayılan | Ne işe yarar |
|---|---|---|---|
| `query` | `keyword`, `q` | — | Sorulacak soru |
| `hl` | `language_code` | `GAM_HL` | Arayüz dili (`tr`, `en`, `de`) |
| `gl` | `country_code` | `GAM_GL` | Ülke kodu (`TR`, `US`) |
| `google_domain` | `se_domain` | `www.google.com` | Örn. `www.google.com.tr` |
| `location` | `location_name` | — | Kanonik konum → `uule`. Örn. `Bursa,Turkey` |
| `uule` | — | — | Kendi uule değeriniz; `location`'ı ezer |
| `device` | — | `desktop` | `desktop` \| `mobile` — ayrı profil, UA ve viewport |
| `track_domains` | — | `[]` | Bu domainler atıf almış mı (alt alan adları dahil) |
| `track_brands` | — | `[]` | Bu ifadeler cevapta geçiyor mu, bağlamıyla |
| `include_blocks` | — | `true` | Yapısal blok çıktısı |
| `include_html` | — | `false` | Cevap kapsayıcısının ham HTML'i |
| `include_screenshot` | — | `false` | Base64 PNG, raporlar için |
| `include_follow_ups` | — | `true` | Önerilen devam soruları |
| `timeout` | — | `GAM_ANSWER_TIMEOUT` | 5–300 sn |
| `cache` | — | `true` | Yakın zamanlı aynı sorguyu tekrar sormaz |

Alias'lar, mevcut bir DataForSEO entegrasyonunu az değişiklikle buraya yöneltebilmeniz için:
`keyword`, `language_code`, `location_name` ve `se_domain` da kabul edilir.

---

## Konfigürasyon

Tüm ayarlar `GAM_` önekli ortam değişkeni (`.env`). Tam liste: [.env.example](.env.example).
Öne çıkanlar:

| Değişken | Varsayılan | Not |
|---|---|---|
| `GAM_API_KEY` | *(boş)* | Boşsa kimlik doğrulama **kapalı** |
| `GAM_POOL_SIZE` | `1` | Eşzamanlı sekme. 2'nin üstüne çıkmayın |
| `GAM_ANSWER_TIMEOUT` | `90` | Cevabın akmasını bekleme sınırı |
| `GAM_STABLE_FOR` | `1.6` | Metin bu kadar değişmezse akış bitti sayılır |
| `GAM_CACHE_TTL` | `900` | `0` = önbellek kapalı |
| `GAM_BATCH_DELAY` | `2.5` | Toplu sorguda aralardaki bekleme |
| `GAM_CONSENT_CHOICE` | `reject` | Çerez bannerı varsayılanı: **tümünü reddet** |
| `GAM_ANSWER_SELECTORS` | *(config'e bkz.)* | Google DOM'u değişince JSON dizi ile ezin |

---

## Ticari API'lerle karşılaştırma

Bunu gerçekten satan sağlayıcılar var ve çalıştırmak yerine satın almak istiyorsanız makul
seçenekler. **Ağustos 2026** itibarıyla, kabaca — fiyatları kendiniz doğrulayın:

| Sağlayıcı | AI Mode desteği | Yaklaşık fiyat | Model |
|---|---|---|---|
| [DataForSEO](https://dataforseo.com/pricing/serp/google-ai-mode-serp-api) | `serp/google/ai_mode`, live + standard (normal/yüksek öncelik), advanced + HTML uçları | **$0.004 / sayfa**'dan (live), $50 minimum yükleme | Kullandıkça öde |
| [SerpApi](https://serpapi.com/google-ai-mode-api) | `engine=google_ai_mode`; `text_blocks`, `references`, alışveriş/yerel sonuçlar, görsel & video, çok turlu devam soruları, markdown çıktı | 5 000 sorgu için **$75 / ay**'dan, 100 ücretsiz | Abonelik |
| [Bright Data](https://brightdata.com/blog/web-data/best-serp-apis) | SERP API | ~**$3 / 1 000** sonuç, planlar $499/ay'dan | PAYG + abonelik |
| [Oxylabs](https://oxylabs.io/blog/best-serp-api) | SERP Scraper API, başarı başına ödeme | ~**$0.80–1.00 / 1 000** | Abonelik kademeleri |
| **Bu proje** | Yalnızca AI Mode | sadece sunucu maliyeti | Kendi sunucunuzda |

**Satın alın** — günde binlerce sorgu, garantili uptime, proxy havuzu ve Google markup'ı
değiştiğinde arayacak birileri gerekiyorsa.

**Bunu çalıştırın** — günde birkaç yüz sorgu yetiyorsa, ham HTML ve ekran görüntüsü
istiyorsanız, kendi metriklerinizi eklemek istiyorsanız ya da sorgu başına fatura
istemiyorsanız. Proxy havuzu yok, SLA yok, tek IP var.

Yol haritasında, yukarıdaki sağlayıcılardan açıkça ödünç alınanlar: tek oturumda çok turlu
devam soruları, alışveriş / yerel / video bloklarının ayıklanması ve token açısından verimli
`output=md` yanıt biçimi.

---

## Bilinen sınırlar

Tasarım gereği, açıkça:

- **Tek IP, proxy havuzu yok.** Sık sorguda Google doğrulama ekranı çıkarır; API `503 blocked`
  döner. Hacim için `GAM_BROWSER_ARGS` ile önüne residential proxy koyun (`--proxy-server=…`).
- **İlk gün doğrulama ekranı görmeyi bekleyin.** Tanınmayan bir IP'deki soğuk profil çoğu
  zaman ilk birkaç istekte "sıra dışı trafik" sayfasına düşer; bu normal, hata değil. Bir kez
  elle çözün (bkz. *Profil bakımı*), oluşan çerez genelde durumu yatıştırır. Burada
  `GAM_BROWSER_CHANNEL=chromium` önemli: aksi halde Playwright `headless-shell` ikilisini
  çalıştırır ve o, tam tarayıcıya göre gözle görülür biçimde daha hızlı işaretlenir.
- **CAPTCHA aşılmaz.** Doğrulama ekranı çıktığında istek bilerek başarısız olur.
  `scripts/login.py` ile görünür tarayıcıda elle temizleyebilirsiniz.
- **Selector'lar kırılgan.** Google'ın DOM'u obfuscated ve sık değişiyor. Bu yüzden üç katman:
  yapılandırılabilir selector listesi → "en büyük metin bloğu" heuristiği → yenisini bulmak
  için `/v1/debug/html`. `extracted_by` alanı hangisinin devreye girdiğini söyler.
- **`uule` kodlaması resmî değil.** Topluluk tarafından çözülmüş biçim; Google yok sayabilir.
  Konum kritikse çıktıyı doğrulayın ya da kendi `uule` değerinizi geçin.
- **Görevler bellekte.** Yeniden başlatma kuyruğu siler. Kalıcılık için Redis/Postgres ekleyin.
- **AI Mode her sorguda çıkmaz.** Google bazı sorgularda yapay zekâ cevabı üretmez;
  `502 no_answer` alırsınız.

---

## Profil bakımı

Çerezler ve oturum `profile` adlı Docker volume'unda, `/data/profile/{desktop,mobile}`
altında durur. Adlandırılmış volume kullanılıyor: imajdaki `app:app` sahipliği böylece
korunuyor — uygulama root olarak çalışmadığı için taze bir bind mount dizinine yazamazdı.

Doğrulama ekranına takılırsanız, ekranı olan bir makinede profili elle hazırlayıp kopyalayın:

```bash
pip install playwright && playwright install chromium
python scripts/login.py --profile ./profile-desktop     # açılan pencerede çözün, kapatın
docker compose cp ./profile-desktop google-ai-mode-api:/data/profile/desktop
docker compose restart
```

Bind mount tercih ederseniz `docker-compose.yml` içindeki volume satırını
`./data/profile:/data/profile` yapın ve önce `mkdir -p data/profile && sudo chown -R 1000:1000 data`
çalıştırın — aksi halde container profil dizinini oluşturamaz ve başlamaz.

---

## Geliştirme

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && playwright install chromium
uvicorn app.main:app --reload
```

Testler saf analiz fonksiyonlarını kapsar, tarayıcı gerektirmez:

```bash
pytest -q
```

```
app/
  main.py       FastAPI uçları, kimlik doğrulama, hata eşlemesi
  scraper.py    Sayfayı sürer, akışın bitmesini bekler, ayıklar
  browser.py    Cihaz başına kalıcı Chromium profili + sayfa havuzu
  js/extract.js DOM → blok + markdown + atıf
  analysis.py   Domain payı, marka takibi, istatistikler
  tasks.py      Async görev kuyruğu + postback
  cache.py      TTL önbellek
  uule.py       Konum kodlaması
scripts/login.py  Profili hazırlamak için görünür tarayıcı
```

---

## Katkı

**Issue açmaktan çekinmeyin — bunu ayakta tutmanın en hızlı yolu bu.**

Google markup'ını haber vermeden değiştiriyor; kırılma istisna değil, beklenen durum.
Selector düzeltmeleri hızlı çıkıyor ve iyi bir hata raporu işin çoğunu hallediyor:

- **Ayıklama bozulduysa:** sorguyu, `hl`/`gl`/`device` değerlerini ve `extracted_by` alanını
  yazın. `GAM_DEBUG_ENDPOINTS=true` ile alınan `/v1/debug/html` çıktısı çok işe yarar.
- **Atıflar yanlış/eksikse:** `citations` dizisini ve beklediğinizi paylaşın.
- **Özellik fikirleri memnuniyetle** — özellikle bir cevaptan hesaplanabilecek SEO/GEO
  metrikleri.

Selector güncellemeleri, yeni ayıklayıcılar ve dil kapsamı için PR'lar açığa. `pytest -q`
yeşil kalsın yeter.

---

## Sorumluluk

Bu araç Google'ın herkese açık arama sonuçlarını otomatikleştirir. Google'ın kullanım şartları
otomatik erişimi kısıtlar; kullanım sorumluluğu size aittir. Doğrulama ekranlarını aşmaya
yönelik hiçbir mekanizma içermez ve içermeyecektir. Makul hızda, kendi araştırmanız için
kullanın.

## Lisans

MIT — bkz. [LICENSE](LICENSE).
