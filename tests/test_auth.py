"""Anahtar dogrulamasinin iki basligi da kabul ettigini garanti eder.

Bu dosya bir hatanin ardindan yazildi. require_key yalnizca X-API-Key okuyordu;
oysa OpenAI istemcilerinin tamami (Open WebUI, LangChain, Cursor, openai-python)
anahtari Authorization: Bearer olarak yollar ve X-API-Key hic gondermez. Sonuc:
anahtar tanimli her kurulumda /v1/chat/completions 401 veriyordu -- projenin en
ayirt edici ozelligi tam da ise yarayacagi yerde kiriliydi ve hicbir test bunu
yakalamadi, cunku o zaman API katmaninin hic testi yoktu.
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.main import require_key, settings

KEY = "gizli-anahtar-123"


def check(x_api_key=None, authorization=None):
    """require_key'i cagirir; 401 atarsa False, gecerse True doner."""
    try:
        asyncio.run(require_key(x_api_key=x_api_key, authorization=authorization))
        return True
    except HTTPException as e:
        assert e.status_code == 401
        return False


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(settings, "api_key", KEY)


@pytest.fixture
def without_key(monkeypatch):
    monkeypatch.setattr(settings, "api_key", "")


class TestKeyConfigured:
    def test_x_api_key_accepted(self, with_key):
        assert check(x_api_key=KEY)

    def test_bearer_accepted(self, with_key):
        """Asil regresyon: OpenAI istemcileri sadece bunu gonderir."""
        assert check(authorization=f"Bearer {KEY}")

    def test_bearer_scheme_is_case_insensitive(self, with_key):
        # RFC 7235 semasi buyuk/kucuk harf duyarsiz; istemciler "bearer" da yollar.
        assert check(authorization=f"bearer {KEY}")

    def test_bearer_value_is_trimmed(self, with_key):
        assert check(authorization=f"Bearer  {KEY}  ")

    def test_wrong_bearer_rejected(self, with_key):
        assert not check(authorization="Bearer yanlis")

    def test_wrong_x_api_key_rejected(self, with_key):
        assert not check(x_api_key="yanlis")

    def test_no_header_rejected(self, with_key):
        assert not check()

    def test_basic_scheme_rejected(self, with_key):
        """Anahtar dogru olsa bile Bearer disi bir sema kabul edilmemeli."""
        assert not check(authorization=f"Basic {KEY}")

    def test_bare_key_without_scheme_rejected(self, with_key):
        assert not check(authorization=KEY)

    def test_x_api_key_wins_when_both_sent(self, with_key):
        """X-API-Key varsa o kullanilir; dogruysa gecer, yanlissa Bearer kurtarmaz."""
        assert check(x_api_key=KEY, authorization="Bearer yanlis")
        assert not check(x_api_key="yanlis", authorization=f"Bearer {KEY}")


class TestNoKeyConfigured:
    """GAM_ALLOW_NO_AUTH ile acilan kurulumda hicbir baslik istenmez."""

    def test_everything_passes(self, without_key):
        assert check()
        assert check(x_api_key="alakasiz")
        assert check(authorization="Bearer alakasiz")
