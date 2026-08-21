"""Fixture'lar herkese acik repoda duruyor; icinde sir kalmadigini garanti eder.

Bu dosya bir gecmisin urunu: gercek bir AI Mode sayfasi yakalandiginda icinde
Google'in kendi public browser key'i (data-api="AIza...") de geldi ve fark edilmeden
repoya girdi. Google'in kendi anahtariydi, bize ait bir kimlik bilgisi degildi -- ama
halka acik bir depoda gercek anahtar dizisi durmasi secret tarayicilarini tetikler.
Yeni fixture eklendiginde ayni sey tekrarlanmasin diye kontrol testte.
"""

import re
from pathlib import Path

import pytest

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.html"))

# Desen -> ne oldugu. Fixture'a yeni bir kaynak eklerken bu listeyi genisletin.
SECRET_PATTERNS = {
    "Google API anahtari": r"AIza[0-9A-Za-z_\-]{35}",
    "Google OAuth token": r"ya29\.[0-9A-Za-z_\-]{20,}",
    "AWS erisim anahtari": r"AKIA[0-9A-Z]{16}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{36}",
    "OpenAI anahtari": r"sk-[A-Za-z0-9]{32,}",
    "Ozel anahtar blogu": r"BEGIN (?:RSA |OPENSSH |EC |PGP )?PRIVATE KEY",
    "e-posta adresi": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "Google profil gorseli": r"lh\d\.googleusercontent\.com",
}


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
@pytest.mark.parametrize("label,pattern", SECRET_PATTERNS.items(), ids=lambda v: v if isinstance(v, str) else "")
def test_fixture_has_no_secrets(path, label, pattern):
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = re.findall(pattern, text)
    assert not hits, (
        f"{path.name} icinde {label} bulundu ({len(hits)} adet): {hits[0][:24]}... "
        f"Fixture herkese acik repoda; yakalama sirasinda temizlenmeli "
        f"(bkz. tests/fixtures/README.md)."
    )
