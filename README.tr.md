# Google AI Mode API

**Google AI Mode (`udm=50`) cevaplarını JSON döndüren, kendi sunucunuzda çalışan API.
SEO / GEO araştırması için.**

[![Sürüm](https://img.shields.io/github/v/release/TurkerYakup/google-ai-mode-api?color=success&label=s%C3%BCr%C3%BCm)](https://github.com/TurkerYakup/google-ai-mode-api/releases/latest)
[![CI](https://github.com/TurkerYakup/google-ai-mode-api/actions/workflows/ci.yml/badge.svg)](https://github.com/TurkerYakup/google-ai-mode-api/actions/workflows/ci.yml)
[![Lisans: MIT](https://img.shields.io/badge/lisans-MIT-blue.svg)](LICENSE)
[![Container](https://img.shields.io/badge/ghcr.io-google--ai--mode--api-2496ed?logo=docker&logoColor=white)](https://github.com/TurkerYakup/google-ai-mode-api/pkgs/container/google-ai-mode-api)

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
git clone https://github.com/TurkerYakup/google-ai-mode-api.git
cd google-ai-mode-api
cp .env.example .env
```

Anahtar verin — **anahtarsız servis açılmaz**:

```bash
sed -i "s/^GAM_API_KEY=.*/GAM_API_KEY=$(openssl rand -hex 32)/" .env
```

Hazır imajı çekin (derleme yok, Chromium ile ~2 GB):

```bash
docker compose pull && docker compose up -d
```

Ya da kaynaktan derleyin:

```bash
docker compose up -d --build
```

> Yalnızca localhost'ta çalıştırıyor ve anahtar istemiyor musunuz? `.env` içinde
> `GAM_ALLOW_NO_AUTH=true` yapın. Bu bilinçli bir muafiyettir ve servis her açılışta
> uyarı loglar.

```bash
curl http://127.0.0.1:8000/health
```

Swagger arayüzü: <http://127.0.0.1:8000/docs>

> Port yalnızca `127.0.0.1`'e bağlıdır. `docker-compose.yml` içindeki bu satırı
> değiştirmeden **önce `GAM_API_KEY` verin**.

### Tarayıcı profilini hazırlayın — ilk sorgudan önce

**Taze bir IP üzerindeki soğuk profil, genellikle ilk birkaç istekte Google'ın "olağandışı
trafik" ekranını görür.** İlk çalıştırmada en sık yaşanan şey budur ve bu serviste bir hata
değildir. Kafa karıştırıcı bir `503 blocked` aldıktan sonra değil, şimdi halledin.

Ekranı olan bir makinede:

```bash
pip install playwright && playwright install chromium
python scripts/login.py --profile ./profile-desktop   # açılan pencerede doğrulamayı geçin, kapatın
docker compose cp ./profile-desktop google-ai-mode-api:/data/profile/desktop
docker compose restart
```

Bunun ürettiği çerez işleri yatıştırır. Burada iki şey önemli:

- **Oturum açmayın.** Kendi Google hesabınızı kullanmayın —
  [Tarayıcı profilinin bakımı](#tarayıcı-profilinin-bakımı) bölümüne bakın. IP engeli
  saatler içinde kalkar, hesap askıya alınması kalkmaz.
- **`GAM_BROWSER_CHANNEL=chromium` kalsın** (varsayılan). Aksi halde Playwright kendi
  `headless-shell` ikilisini çalıştırır ve Google onu tam tarayıcıdan belirgin şekilde
  daha hızlı işaretler.

Bu adımı atlamak çoğu zaman yürür, önce bir sorgu deneyebilirsiniz — sadece `503 blocked`
görünce ne olduğunu bilin.

### Tek sorgu

```bash
curl -s -X POST http://127.0.0.1:8000/v1/query \
  -H 'Content-Type: application/json' \
  -d '{
        "query": "Bursa yapay zeka firmaları",
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

AI Mode cevabı ölçülen ~10-15 sn akar, uç durumda daha uzun. Uzun keyword kümelerinde ya da
bekleyemeyen istemcilerde görev aç, ID al, sonra sonucu çek — ya da bitince webhook'unuza
POST edilsin:

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
        "tag": "crm-kumesi"
      }'
```

Görevler **sırayla**, aralarında `GAM_BATCH_DELAY` saniye bekleyerek işlenir. Bu kasıtlı:
paralel gitmek Google'ın doğrulama ekranını çağırmanın en hızlı yoludur.

---

### LLM olarak kullanma (OpenAI uyumlu)

Hiçbir SERP sağlayıcısının satmadığı kısım bu: AI Mode'un sohbet modeli olarak sunulması.
Open WebUI, LangChain, Cursor, `openai-python` — OpenAI API'si konuşan ne varsa
`http://127.0.0.1:8000/v1` adresine yöneltin, ara katman gerekmiyor. Model kimliği
`google-ai-mode`, API anahtarı da `GAM_API_KEY`.

```bash
curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GAM_API_KEY" \
  -d '{
        "model": "google-ai-mode",
        "messages": [{"role": "user", "content": "crm nedir"}]
      }'
```

Akış için `"stream": true` ekleyin. Hem `Authorization: Bearer` (OpenAI istemcilerinin
gönderdiği) hem `X-API-Key` kabul edilir.

> **Akış taklit.** Google cevabın tamamını API görmeden önce üretiyor; dolayısıyla yanıt
> üretildiği anda değil, sonradan parçalara bölünüyor. İstemciler farkı anlamaz ama ilk
> parçaya kadar geçen süre sorgunun tam gecikmesidir — gerçek bir modelin verdiği saniye
> altı değil, ~10-15 saniye.

---

## Uçlar

| Method | Yol | Açıklama |
|---|---|---|
| `GET` | `/health` | Durum, tarayıcı havuzları, bekleyen görev sayısı |
| `POST` | `/v1/query` | Tek sorgu, senkron |
| `GET` | `/v1/query?q=…` | Tek sorgu, senkron, pratik biçim |
| `POST` | `/v1/batch` | Keyword listesi, senkron (5'ten fazlası için görev kullanın) |
| `POST` | **`/v1/chat/completions`** | **OpenAI uyumlu sohbet, akışlı ya da akışsız — aşağıya bakın** |
| `GET` | **`/v1/models`** | **OpenAI uyumlu model listesi, yoklayan istemciler için** |
| `POST` | `/v1/tasks/query` | Tek sorguyu kuyruğa atar → `202` + `task_id` |
| `POST` | `/v1/tasks/batch` | Keyword listesini kuyruğa atar |
| `GET` | `/v1/tasks/{id}` | Görev durumu ve sonucu |
| `GET` | `/v1/tasks?status=done` | Görev listesi |
| `DELETE` | `/v1/cache` | Önbelleği temizler |
| `POST` | `/v1/browser/restart` | Chromium'u yeniden başlatır |
| `GET` | `/v1/debug/html?q=…` | Ham HTML, selector düzeltmek için (kapalı gelir) |
| `GET` | `/v1/debug/screenshot?q=…` | Tam sayfa PNG, base64 |

`GAM_API_KEY` doluysa tüm `/v1/*` uçları anahtarı ister; `X-API-Key` başlığıyla da
`Authorization: Bearer` ile de verilebilir. **`/v1/models` bilinçli istisnadır** — OpenAI
istemcileri kimlik bilgisi girilmeden önce bağlantıyı sınamak için burayı yoklar ve uç
sabit bir model kimliğinden başka bir şey döndürmez.

### Hatalar

FastAPI'nin kendi hataları dahil **her hata aynı gövdeyle** döner; tek bir şekil işlemeniz
yeterli:

```json
{
  "status": "error",
  "code": "blocked",
  "message": "Google bu isteği doğrulama ekranına yönlendirdi (CAPTCHA / olağandışı trafik).",
  "detail": "İstek hızını düşürün, farklı bir IP kullanın veya profili tarayıcıda elle tazeleyin."
}
```

| HTTP | `code` | Ne oldu | Ne yapmalı |
|---|---|---|---|
| `400` | `bad_request` | Sohbet isteğinde boş olmayan `user` mesajı yok ya da `GAM_MAX_BATCH_SIZE`'ı 50'nin altına çekmişseniz onu aşan toplu istek | İsteği düzeltin |
| `401` | `unauthorized` | `X-API-Key` eksik veya yanlış | `GAM_API_KEY`'deki anahtarı gönderin |
| `404` | `not_found` | Bilinmeyen `task_id` ya da debug uçları kapalı | Görev sonuçları `GAM_TASK_RETENTION` sonrası silinir; debug için `GAM_DEBUG_ENDPOINTS=true` |
| `422` | `validation_error` | Gövde veya parametreler doğrulamadan geçmedi — boş `query`, tanımsız `device`, 50'den fazla maddelik toplu istek | `detail` alanı alan bazında hataları taşır |
| `500` | `internal_error` | Beklenmeyen hata | `docker compose logs` |
| `502` | `no_answer` | Sayfa açıldı ama AI Mode cevabı bulunamadı | Google bazı sorgularda yapay zekâ cevabı üretmez. Her sorguda oluyorsa DOM değişmiştir — `extracted_by` ve `GAM_ANSWER_SELECTORS`'a bakın |
| `502` | `extract_failed` | Ayıklama betiği sayfa içinde hata verdi | Genelde DOM değişikliği; sorguyla birlikte issue açın |
| `503` | `blocked` | Google doğrulama ekranı verdi (`/sorry/index`) | **En sık görülen.** Hız tavanına çarptınız — [Ölçülen limitler](#ölçülen-limitler). Bekleyin, yavaşlayın ya da `GAM_PROXY_SERVER` verin |
| `503` | `browser_unavailable` | Kuyruk süresi içinde boş sekme çıkmadı ya da profil dizini yazılabilir değil | `GAM_POOL_SIZE`'ı artırın ya da volume sahipliğini düzeltin — mesaj hangisi olduğunu söyler |
| `504` | `navigation_timeout` | Sayfa `GAM_NAV_TIMEOUT` içinde açılmadı | Ağ ya da Google yavaş; tekrar deneyin |

Toplu yanıtlarda her madde kendi hatasını `items[].error` altında aynı `code` / `message`
ile taşır, toplu isteğin kendisi yine `200` döner.

---

## İstek parametreleri

| Alan | Alias | Varsayılan | Ne işe yarar |
|---|---|---|---|
| `query` | `keyword`, `q` | — | Sorulacak soru |
| `hl` | `language_code` | `GAM_HL` | Arayüz dili (`tr`, `en`, `de`) |
| `gl` | `country_code` | `GAM_GL` | Ülke kodu (`TR`, `US`) |
| `google_domain` | `se_domain` | `www.google.com` | Örn. `www.google.com.tr` |
| `location` | `location_name` | — | Kanonik konum → `uule`. **Ölçüldü, etkisiz — aşağıya bakın** |
| `uule` | — | — | Kendi uule değeriniz; `location`'ı ezer. Aynı çekince geçerli |
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

Aşağıdaki fiyatlar **22 Ağustos 2026**'da her sağlayıcının kendi fiyat sayfasından okundu.
Değişirler; güvenmeden önce bağlantılara bakın.

| Sağlayıcı | AI Mode desteği | Fiyat | Model |
|---|---|---|---|
| [DataForSEO](https://dataforseo.com/pricing/serp/google-ai-mode-serp-api) | AI Mode'a özel SERP API | SERP başına **$0.0012** standart kuyruk (~5 dk), **$0.0024** öncelikli (~1 dk), **$0.004** live (~6 sn) | Kullandıkça öde, [$50 minimum yükleme](https://dataforseo.com/help-center/minimum-payment) (devreder, $1 deneme kredisi) |
| [SerpApi](https://serpapi.com/google-ai-mode-api) | `engine=google_ai_mode`; `text_blocks`, `references`, `related_questions`, `shopping_results`, `reconstructed_markdown`, çok tur için `subsequent_request_token` | 250 sorgu ücretsiz; **$25** / 1 000, $75 / 5 000, $275 / 30 000, $3 750 / 1 M'e kadar. AI Mode için ek ücret yok | Abonelik, kullandıkça öde seçeneği yok |
| [Bright Data](https://brightdata.com/pricing/serp) | Genel SERP API — fiyat sayfasında AI Mode belirtilmiyor | **$1.50 / 1 000** PAYG; Scale $499/ay 380 K dahil, sonrası $1.30 / 1 000; ayda 5 K ücretsiz | PAYG + abonelik |
| [Oxylabs](https://oxylabs.io/products/scraper-api/serp/pricing) | Web Scraper API — AI Mode'a özel ürün bulunamadı | $49 Micro planında Google ~**$1.00 / 1 000**; $99 / $249 kademeleri; başarılı istek başına ücret; 2 K ücretsiz deneme | Abonelik kademeleri |
| **Bu proje** | Yalnızca AI Mode | Sadece sunucu maliyeti | Kendi sunucunuzda |

### Maliyet argümanı konusunda dürüst olalım

DataForSEO'nun standart kuyruğunda 1 000 AI Mode sayfası **$1.20**. Bu projenin ölçülen
tavanı tek residential IP'de saatte ~40 sorgu — günde ~960, ki bunu yaklaşık **günde $1.15**'e
satın alabilirsiniz. Yani *bunu çalıştırmanın sebebi maliyet değil.*

Ayakta duran sebepler:

- **AI Mode'un OpenAI API'si üzerinden sohbet modeli olması.** Open WebUI, LangChain ya da
  Cursor'u `/v1`'e yöneltin, Google'ın AI Mode'u model listesinde bir seçenek hâline gelir.
  **Hiçbir SERP sağlayıcısı bunu satmıyor** — onlar parse etmeniz için JSON döndürür, mevcut
  bir LLM istemcisine takabileceğiniz bir şey değil.
  Bkz. [LLM olarak kullanma](#llm-olarak-kullanma-openai-uyumlu).
- **`blocks[].links` atıfları tek tek iddialara bağlıyor.** Sağlayıcılar düz bir kaynak
  listesi döndürür; burada hangi cümlenin hangi kaynağa dayandığı eşleşir.
- **GEO metrikleri hazır geliyor** — domain payı, bağlamıyla marka geçişleri, domain takibi.
  Diğerlerinde SERP'i parse edip bunları kendiniz hesaplarsınız.
- **Sorgularınız makinenizden çıkmıyor.** Müşteri markası takip ediyorsanız önemli.
- **Minimum yok, abonelik yok, sorgu başına fatura yok.**

**Satın alın** — hacim, garantili uptime, proxy havuzu, doğrulanmış konum hedefleme ya da
Google markup'ı değiştiğinde arayacak birileri gerekiyorsa.

---

## Ölçülen limitler

Tek bir ev IP'sinden (Türkiye, residential), `GAM_POOL_SIZE=1`, tam Chromium
(`GAM_BROWSER_CHANNEL=chromium`), 22 Ağustos 2026'da ölçüldü:

| Ölçüm | Değer |
|---|---|
| Sorgu başına süre | **~10-11 sn** (medyan; ilk sorgu ~14 sn) |
| 5 sn aralıkla ardışık sorgu | **15/15 sorunsuz** (≈4 sorgu/dk, 232 sn) |
| Aralıksız ardışık sorgu | **28 sorunsuz, 29.'da engel** (≈5.5 sorgu/dk, 311 sn) |
| Toplam eşik | Yaklaşık **43 sorgu / ~10 dakika** |
| Engel biçimi | `503 blocked`, anında (~1 sn), `/sorry/index` |

Kritik ayrıntı: engel iki koşumun **toplamında** 44. istekte geldi. Yani bu saf bir
hız limiti değil, biriken bir bütçe gibi davranıyor — yavaşlatmak eşiği geciktirir
ama kaldırmaz. Engellendikten sonra toparlanma saatler sürebiliyor.

Pratik kapasite: **saatte ~40 sorgu**, kümeler arasında ara vererek. Daha fazlası
için proxy şart (`GAM_PROXY_SERVER`).

### Healthcheck hiçbir şeyi yeniden başlatmaz

`docker-compose.yml` bir healthcheck tanımlıyor ama `restart: unless-stopped` **sağlık
durumuna bakmaz** — unhealthy olan container öyle kalır ve çalışmaya devam eder.
Healthcheck size bir sinyaldir, kendi kendini onarma mekanizması değil.

Ya `/health`'i dışarıdan izleyin (Uptime Kuma, cron ile curl, kendi izleme sisteminiz),
ya da duruma göre hareket eden bir gözetmen ekleyin:

```yaml
  autoheal:
    image: willfarrell/autoheal
    restart: always
    environment:
      AUTOHEAL_CONTAINER_LABEL: autoheal
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

ve bu servise `autoheal: "true"` etiketini verin. Şunu da bilin: buradaki arıza
biçimlerinin çoğu yeniden başlatmayla düzelmez — `503 blocked` Google'ın sizi
reddettiği anlamına gelir, container'ı yeniden başlatmak bunu değiştirmez.

### Bellek

Container'ın cgroup'undan ~25 sorgu sonrası ölçüldü: **922 MiB kullanımda, 1.34 GiB tepe,
2 GiB limite karşı.** OOM yok, restart yok. `GAM_PAGE_RECYCLE_AFTER=25` sekmeyi geri
dönüştürerek bunu düz tutuyor; `POST /v1/browser/restart` başlangıç seviyesine döndürüyor
ve sürekli çalışan kurulumlarda periyodik çağrılmaya değer.

> **Önceki sürümler burada daha yüksek rakamlar veriyordu (980 MB → 1.37 GB) ve yanlıştı.**
> `/health`, `memory_mb`'yi `/proc/*/statm`'daki süreç başına RSS'leri toplayarak
> hesaplıyordu. Chromium onlarca süreç açar ve hepsi aynı kütüphane ile grafik sayfalarını
> paylaşır; bu toplama ise paylaşılan her sayfayı her süreçte yeniden sayar. Yük altında
> yaklaşık 2.5 kat şişiriyordu: cgroup 922 MiB derken 2325 MB gösteriyordu. Container
> limitin %45'indeyken limitin **üstünde** bir sayı gösterebiliyordu. 0.3.1'den itibaren
> `memory_mb`, her sayfayı bir kez sayan ve `docker stats` ile uyuşan
> `/sys/fs/cgroup/memory.current` dosyasını okuyor.

---

## Bilinen sınırlar

Tasarım gereği, açıkça:

- **Tek IP, proxy havuzu yok.** Sık sorguda Google doğrulama ekranı çıkarır; API `503 blocked`
  döner. Hacim için `GAM_BROWSER_ARGS` ile önüne residential proxy koyun (`--proxy-server=…`).
- **İlk gün doğrulama ekranı görmeyi bekleyin.** Tanınmayan bir IP'deki soğuk profil çoğu
  zaman ilk birkaç istekte "sıra dışı trafik" sayfasına düşer; bu normal, hata değil. Yeterince
  sık yaşandığı için hızlı başlangıcın bir adımı hâline getirildi:
  [Tarayıcı profilini hazırlayın](#tarayıcı-profilini-hazırlayın--ilk-sorgudan-önce).
- **CAPTCHA aşılmaz.** Doğrulama ekranı çıktığında istek bilerek başarısız olur.
  `scripts/login.py` ile görünür tarayıcıda elle temizleyebilirsiniz.
- **Selector'lar kırılgan.** Google'ın DOM'u obfuscated ve sık değişiyor. Bu yüzden üç katman:
  yapılandırılabilir selector listesi → "en büyük metin bloğu" heuristiği → yenisini bulmak
  için `/v1/debug/html`. `extracted_by` alanı hangisinin devreye girdiğini söyler.
- **Konum hedefleme çalışmıyor. Sonuçlar sunucunun IP adresine göre geliyor.**
  Bu varsayım değil, ölçüm. Aynı Türkçe soru `location=Berlin,Germany` ve
  `location=Istanbul,Turkey` ile sorulduğunda iki seferde de aynı cevap döndü —
  üstelik cevap, test makinesinin fiziksel olarak bulunduğu **Bursa**'daki
  restoranlarla ilgiliydi. Berlin isteği tek bir `.de` domaini bile göstermedi,
  metinde "Berlin" hiç geçmedi.

  Atıf domainlerinin örtüşmesi metrik olarak denendi ve işe yaramadı. İki koşumda
  **aynı** konum iki kez sorulduğunda örtüşme %31 ve %43, **iki farklı** şehirde ise
  %26 ve %8 çıktı. Her koşulda tek örneklem varken bu kadar oynak bir sayı istenen
  her şeyi söyletebilir — bu yüzden hüküm nitel sinyale dayanıyor: Berlin iste, Alman
  kaynağı say. Hiç yok.

  Bunun iki sonucu var. Birincisi, `uule` kodlaması topluluk tarafından çözülmüş
  gayriresmî biçim ve Google AI Mode'da bunu görmezden geliyor. İkincisi — asıl tuzak
  bu — `resolved_location` alanı ne istediyseniz onu aynen geri yazıyor, dolayısıyla
  yanıt konum uygulanmış **gibi görünüyor**. O alanı "istenen konum" olarak okuyun,
  asla onay olarak değil.

  Parametreler yine de kabul ediliyor: hem mevcut çağrılar bozulmasın diye, hem de
  Google davranışını değiştirirse diye. Bugün gerçekten konuma özel sonuç gerekiyorsa
  tek işe yarayan yol, container'ı o konumdaki bir proxy üzerinden geçirmek
  (`GAM_PROXY_SERVER`). Ölçümün kapsamı: tek sorgu, tek dil, iki şehir, tek IP —
  "çalışıyor" iddiasını çürütmeye yeter, "hiç çalışmaz" demeye yetmez.
- **Görevler bellekte.** Yeniden başlatma kuyruğu siler. Kalıcılık için Redis/Postgres ekleyin.
- **AI Mode her sorguda çıkmaz.** Google bazı sorgularda yapay zekâ cevabı üretmez;
  `502 no_answer` alırsınız.
- **`answer` sonunda kaynak kartları yer alır.** Google, cevabın altındaki kaynak
  kartlarını (başlık + snippet + domain) aynı kapsayıcının içine koyuyor; bunlar
  cevabın düz yazısı değil ama `answer` metnine ve `stats.words` sayısına dahil
  oluyor. Ayırmayı denedik, bu DOM'da güvenilir bir sinyal yok: sınıf adları
  obfuscated, kart ile düz yazı listesi aynı yapıda ve tüm `<a>` elemanlarının
  metni boş. Analizde kelime sayısı kritikse `blocks` dizisinin son liste
  bloklarını dışarıda bırakın.
- **Devam soruları (`follow_ups`) çoğu zaman boş döner.** Doğrulanmış Türkçe
  yakalamada AI Mode bu önerileri hiç göstermiyordu — sayfanın tamamında soru
  biçiminde tek bir öğe yoktu. Kod duruyor, farklı dil/düzenlerde dolabilir.

---

## Profil bakımı

> ### ⚠️ Kendi Google hesabınızla giriş yapmayın
>
> **En büyük risk IP değil, hesap.** Profil sürekli otomasyon için kullanılıyor; oturum
> açıkken çalıştırırsanız Google trafiği IP'ye değil **hesaba** bağlar. IP engeli birkaç
> saatte geçer — **hesap askıya alınması kalıcıdır** ve itiraz süreci sancılıdır.
>
> Doğrusu: **oturum kapalı kalın.** Bu servis oturum gerektirmiyor; doğrulanmış tüm
> ölçümler oturum kapalı yapıldı. İlla gerekiyorsa yalnızca bu iş için açılmış,
> kaybı önemsiz, tek kullanımlık bir hesap kullanın — asıl hesabınızı asla.

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
İyi bir hata raporu işin çoğunu hallediyor:

- **Ayıklama bozulduysa:** sorguyu, `hl`/`gl`/`device` değerlerini ve `extracted_by` alanını
  yazın. `GAM_DEBUG_ENDPOINTS=true` ile alınan `/v1/debug/html` çıktısı çok işe yarar.
- **Atıflar yanlış/eksikse:** `citations` dizisini ve beklediğinizi paylaşın.
- **Özellik fikirleri memnuniyetle** — özellikle bir cevaptan hesaplanabilecek SEO/GEO
  metrikleri.

Selector güncellemeleri, yeni ayıklayıcılar ve dil kapsamı için PR'lar açığa. `pytest -q`
yeşil kalsın yeter.

**Bakım konusunda açık olalım:** bu bir yan proje, SLA'lı bir ürün değil. Kendi işimde
kullandığım sürece bakımlı kalır. Selector düzeltmeleri öncelikli — onlar olmadan geri
kalanın anlamı yok; özellik istekleri best-effort. Hata raporuna ekleyebileceğiniz en
faydalı şey, yakalanmış bir sayfa üzerinden regression testidir
([`tests/fixtures/`](tests/fixtures/)) — düzeltmeyi tahmin oyunu olmaktan çıkaran şey odur.
`/health` çıktısındaki sürümü de mutlaka yazın.

---

## Sorumluluk

Bu araç Google'ın herkese açık arama sonuçlarını otomatikleştirir. Google'ın kullanım şartları
otomatik erişimi kısıtlar; kullanım sorumluluğu size aittir. Doğrulama ekranlarını aşmaya
yönelik hiçbir mekanizma içermez ve içermeyecektir. Makul hızda, kendi araştırmanız için
kullanın.

## Lisans

MIT — bkz. [LICENSE](LICENSE).
