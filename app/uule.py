"""Google 'uule' konum parametresi kodlamasi.

Google bu parametreyi belgelemiyor; asagidaki kodlama SEO araclarinda yaygin
kullanilan, kanonik konum adini base64'leyen surumdur. Google yok sayabilir,
bu yuzden sonucta hangi konumun istendigi 'resolved_location' ile geri donulur.
Kendi uule degerinizi elde ettiyseniz istekte dogrudan 'uule' alanini kullanin.
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
