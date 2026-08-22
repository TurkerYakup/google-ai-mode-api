"""Google 'uule' konum parametresi kodlamasi.

Google bu parametreyi belgelemiyor; asagidaki kodlama SEO araclarinda yaygin
kullanilan, kanonik konum adini base64'leyen surumdur.

OLCULDU: AI Mode bunu yok sayiyor. Ayni sorgu Berlin ve Istanbul icin sorulunca
iki seferde de sunucunun fiziksel konumundaki (Bursa) sonuclar dondu; Berlin
isteginde tek bir .de domaini cikmadi. Kontrol kosumu da gerekti, cunku AI Mode
deterministik degil: ayni konum iki kez sorulunca domain ortakligi %31, iki
farkli sehirde %26 -- yani konuma atfedilebilecek fark gurultunun altinda.

Kod yine de duruyor: cagri sozlesmesini bozmamak ve Google davranisini
degistirirse hazir olmak icin. 'resolved_location' alani ISTENEN konumu geri
yazar, uygulandiginin onayi DEGILDIR. Gercekten konuma ozel sonuc gerekiyorsa
tek calisan yol o konumda bir proxy kullanmaktir (GAM_PROXY_SERVER).
"""

import base64

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def encode_uule(canonical_name: str) -> str:
    """'Istanbul,Turkey' gibi bir kanonik konum adini uule degerine cevirir."""
    name = canonical_name.strip()
    if not name:
        raise ValueError("konum adi bos olamaz")
    length_char = _ALPHABET[len(name) % len(_ALPHABET)]
    encoded = base64.b64encode(name.encode("utf-8")).decode("ascii")
    return f"w+CAIQICI{length_char}{encoded}"
