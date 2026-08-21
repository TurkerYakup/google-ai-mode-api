# Google AI Mode API

Google'ın **AI Mode** (`udm=50`) cevaplarını JSON olarak döndüren, Docker içinde çalışan bir API.
SEO / **GEO (Generative Engine Optimization)** araştırması için tasarlandı: cevabın metnini değil,
**hangi kaynakların atıf aldığını, hangi markanın geçtiğini, konuma ve cihaza göre neyin değiştiğini** ölçer.

Resmî bir Google API'si yoktur. Bu servis, Docker içinde headless Chromium (Playwright) ile
AI Mode sayfasını açar, cevabın akması bitene kadar bekler ve sonucu yapılandırılmış JSON'a çevirir.

---

## Ne döndürür

```jsonc
{
  "status": "ok",
  "query": "en iyi crm yazılımı",
  "answer": "## Öne çıkan seçenekler\n- **HubSpot** …",   // markdown
  "blocks": [                                              // yapısal parçalar
    { "type": "paragraph", "text": "…", "links": [ { "url": "…", "domain": "hubspot.com" } ] }
  ],
  "citations": [                                           // görünme sırasına göre
    { "position": 1, "title": "…", "url": "https://…", "domain": "hubspot.com" }
  ],
  "domains": [                                             // domain başına atıf payı
    { "domain": "hubspot.com", "citations": 3, "first_position": 1, "share": 0.375, "urls": ["…"] }
  ],
  "follow_ups": ["CRM fiyatları nedir?"],                  // Google'ın önerdiği devam soruları
  "tracked_domains": [ { "domain": "ornek.com", "cited": true, "positions": [2] } ],
  "tracked_brands": [ { "brand": "Örnek", "mentioned": true, "count": 2, "contexts": ["…"] } ],
  "stats": { "characters": 1840, "words": 260, "citation_count": 8, "unique_domains": 5, "block_count": 12 },
  "source_url": "https://www.google.com/search?q=…&udm=50",
  "device": "desktop", "hl": "tr", "gl": "TR",
  "resolved_location": "Istanbul,Turkey",
  "cached": false, "truncated": false, "elapsed_ms": 24310
}
```

`blocks[].links` en değerli kısım: **hangi cümlenin hangi kaynağa dayandığını** eşleştirir.
Klasik SERP'te "sıra 3'teyiz" derken, AI Mode'da soru "cevabın hangi iddiasında bize atıf var".

---

## Kurulum

```bash
git clone https://github.com/TurkerYakup/google-ai-mode-api.git
cd google-ai-mode-api
cp .env.example .env        # GAM_API_KEY'i doldurun
docker compose up -d --build
```

Sağlık kontrolü:

```bash
curl http://127.0.0.1:8000/health
```

Swagger arayüzü: <http://127.0.0.1:8000/docs>

> Port varsayılan olarak yalnızca `127.0.0.1`'e bağlıdır. Dışarı açacaksanız **önce `GAM_API_KEY` verin**,
> sonra `docker-compose.yml` içindeki port satırını değiştirin.

---

## Kullanım

### Tek sorgu (senkron)

```bash
curl -s -X POST http://127.0.0.1:8000/v1/query \
  -H 'Content-Type: application/json' -H 'X-API-Key: SIZIN_ANAHTARINIZ' \
  -d '{
        "query": "en iyi crm yazılımı",
        "location": "Istanbul,Turkey",
        "device": "desktop",
        "track_domains": ["ornek.com", "rakip.com"],
        "track_brands": ["Örnek"]
      }'
```

Hızlı deneme için GET de var:

```bash
curl "http://127.0.0.1:8000/v1/query?q=en+iyi+crm&track_domains=ornek.com,rakip.com"
```

### Async görev (önerilen)

AI Mode cevabı 30–90 sn sürebilir; çoğu HTTP istemcisi bu kadar beklemez.
Görev aç, ID al, sonucu sonra çek — istersen bitince webhook'a POST edilsin:

```bash
# 1) görevi kuyruğa at
curl -s -X POST http://127.0.0.1:8000/v1/tasks/query \
  -H 'Content-Type: application/json' -H 'X-API-Key: …' \
  -d '{"query":"crm karşılaştırma","tag":"haftalik-tarama","postback_url":"https://sizin-sisteminiz/webhook"}'
# → {"task_id":"a1b2…","status":"queued","poll_url":"/v1/tasks/a1b2…"}

# 2) sonucu al
curl -s http://127.0.0.1:8000/v1/tasks/a1b2… -H 'X-API-Key: …'
```

### Keyword listesi taraması

```bash
curl -s -X POST http://127.0.0.1:8000/v1/tasks/batch \
  -H 'Content-Type: application/json' -H 'X-API-Key: …' \
  -d '{
        "queries": ["crm yazılımı", "crm fiyatları", "ücretsiz crm"],
        "track_domains": ["ornek.com"],
        "location": "Ankara,Turkey",
        "tag": "crm-kumesi"
      }'
```

Görevler **sırayla** işlenir (istekler arası `GAM_BATCH_DELAY` saniye bekleme). Bu kasıtlı:
paralel gitmek Google'ın doğrulama ekranını tetikler.

---

## Uçlar

| Method | Uç | Açıklama |
|---|---|---|
| `GET` | `/health` | Durum, tarayıcı havuzu, bekleyen görev sayısı |
| `POST` | `/v1/query` | Tek sorgu, senkron |
| `GET` | `/v1/query?q=…` | Tek sorgu, senkron, hızlı deneme |
| `POST` | `/v1/batch` | Keyword listesi, senkron (5'ten fazlası için görev kullanın) |
| `POST` | `/v1/tasks/query` | Tek sorguyu kuyruğa atar → `202` + `task_id` |
| `POST` | `/v1/tasks/batch` | Keyword listesini kuyruğa atar |
| `GET` | `/v1/tasks/{id}` | Görev durumu ve sonucu |
| `GET` | `/v1/tasks?status=done` | Görev listesi |
| `DELETE` | `/v1/cache` | Önbelleği temizler |
| `POST` | `/v1/browser/restart` | Chromium'u yeniden başlatır |
| `GET` | `/v1/debug/html?q=…` | Ham HTML (selector güncellemek için, kapalı gelir) |
| `GET` | `/v1/debug/screenshot?q=…` | Sayfa görüntüsü, base64 |

Kimlik doğrulama: `GAM_API_KEY` doluysa tüm `/v1/*` uçları `X-API-Key` başlığı ister.

---

## İsteğe bağlı parametreler

| Alan | Alias | Varsayılan | Ne işe yarar |
|---|---|---|---|
| `query` | `keyword`, `q` | — | Sorulacak soru |
| `hl` | `language_code` | `GAM_HL` | Arayüz dili (`tr`, `en`, `de`) |
| `gl` | `country_code` | `GAM_GL` | Ülke kodu (`TR`, `US`) |
| `google_domain` | `se_domain` | `www.google.com` | `www.google.com.tr` gibi |
| `location` | `location_name` | — | Kanonik konum adı → `uule`. Örn. `Istanbul,Turkey` |
| `uule` | — | — | Hazır uule değeri; verilirse `location` yok sayılır |
| `device` | — | `desktop` | `desktop` \| `mobile` — ayrı profil, ayrı UA/viewport |
| `track_domains` | — | `[]` | Bu domainler atıf almış mı (alt alan adları dahil) |
| `track_brands` | — | `[]` | Bu ifadeler cevap metninde geçiyor mu + bağlam |
| `include_blocks` | — | `true` | Yapısal blok çıktısı |
| `include_html` | — | `false` | Cevap kapsayıcısının ham HTML'i |
| `include_screenshot` | — | `false` | Sayfa PNG'si, base64 (rapora kanıt) |
| `include_follow_ups` | — | `true` | Devam soruları |
| `timeout` | — | `GAM_ANSWER_TIMEOUT` | 5–300 sn |
| `cache` | — | `true` | Aynı sorguyu TTL içinde tekrar sormaz |

Alias'lar DataForSEO'dan geçişi kolaylaştırmak için var: `language_code`, `location_name`,
`se_domain`, `keyword` alanları da kabul edilir.

---

## Konfigürasyon

Tüm ayarlar `GAM_` önekli ortam değişkenleri (`.env`). Tam liste için [.env.example](.env.example).
Öne çıkanlar:

| Değişken | Varsayılan | Not |
|---|---|---|
| `GAM_API_KEY` | *(boş)* | Boşsa kimlik doğrulama **kapalı** |
| `GAM_POOL_SIZE` | `1` | Eşzamanlı sekme. 2'nin üstüne çıkarmayın |
| `GAM_ANSWER_TIMEOUT` | `90` | Cevabın akmasını bekleme sınırı |
| `GAM_STABLE_FOR` | `1.6` | Metin bu kadar değişmezse akış bitti sayılır |
| `GAM_CACHE_TTL` | `900` | 0 = önbellek kapalı |
| `GAM_BATCH_DELAY` | `2.5` | Toplu sorguda istekler arası bekleme |
| `GAM_CONSENT_CHOICE` | `reject` | Çerez onayında varsayılan: **tümünü reddet** |
| `GAM_ANSWER_SELECTORS` | *(bkz. config)* | Google DOM'u değişirse JSON dizi ile ezin |

---

## Bilinen sınırlar

Bunlar tasarım gereği; ticari alternatiflerin çözdüğü, bu servisin çözmediği şeyler:

- **Tek IP.** Proxy havuzu yok. Sık sorguda Google doğrulama ekranı çıkarır ve API `503 blocked` döner.
  Ciddi hacim için önüne bir residential proxy koyup `GAM_BROWSER_ARGS` ile `--proxy-server=…` verin.
- **CAPTCHA aşılmaz.** Doğrulama ekranı çıktığında hata döner; bilerek böyle. Profili elle tazelemek için
  `scripts/login.py` var.
- **Selector'lar kırılgan.** Google DOM'u obfuscated ve sık değişiyor. Bu yüzden üç katmanlı savunma var:
  yapılandırılabilir selector listesi → "en büyük metin bloğu" heuristiği → `/v1/debug/html` ile yeni
  selector bulma. `extracted_by` alanı hangisinin devreye girdiğini söyler.
- **`uule` kodlaması resmî değil.** Topluluk tarafından çözülmüş biçim; Google yok sayabilir.
  Konum kritikse çıktıyı doğrulayın veya kendi `uule` değerinizi geçin.
- **Görevler bellekte.** Yeniden başlatınca kuyruk sıfırlanır. Kalıcılık gerekirse Redis/Postgres ekleyin.
- **AI Mode her sorguda çıkmaz.** Google bazı sorgularda AI cevabı üretmez; bu durumda `502 no_answer` gelir.

---

## Profil bakımı

Çerezler ve oturum `./data/profile/{desktop,mobile}` altında tutulur (bind mount).
Doğrulama ekranına takılırsanız host'ta görünür bir tarayıcı açıp elle çözün:

```bash
pip install playwright && playwright install chromium
python scripts/login.py --profile ./data/profile/desktop
```

Pencereyi kapatınca profil kaydedilir; ardından `docker compose restart`.

---

## Geliştirme

```bash
python -m venv .venv && .venv/Scripts/activate     # Windows
pip install -r requirements.txt && playwright install chromium
uvicorn app.main:app --reload
```

Testler (tarayıcı gerektirmez, saf analiz fonksiyonları):

```bash
pytest -q
```

Dosya düzeni:

```
app/
  main.py       FastAPI uçları, kimlik doğrulama, hata eşlemesi
  scraper.py    Sayfayı sürme, akışın bitmesini bekleme, ayıklama
  browser.py    Cihaz başına kalıcı Chromium profili + sayfa havuzu
  js/extract.js DOM → blok + markdown + atıf dönüşümü
  analysis.py   Domain payı, marka takibi, istatistikler
  tasks.py      Async görev kuyruğu + postback
  cache.py      TTL önbellek
  uule.py       Konum kodlaması
scripts/login.py  Profili elle hazırlamak için görünür tarayıcı
```

---

## Sorumluluk

Bu araç Google'ın herkese açık arama sonuçlarını otomatikleştirir. Google'ın kullanım şartları
otomatik erişimi kısıtlar; kullanım sorumluluğu size aittir. Doğrulama ekranlarını aşmaya yönelik
hiçbir mekanizma içermez ve içermeyecektir. Makul hızda, kendi araştırmanız için kullanın.

## Lisans

MIT — bkz. [LICENSE](LICENSE).
