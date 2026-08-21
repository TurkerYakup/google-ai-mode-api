from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GAM_", env_file=".env", extra="ignore")

    # --- HTTP ---
    api_key: Optional[str] = None
    """X-API-Key ile korunur. Bos birakilirsa kimlik dogrulama kapalidir."""
    debug_endpoints: bool = False
    """/v1/debug/* uclarini acar (ham HTML + ekran goruntusu). Sadece gelistirme icin."""

    # --- Tarayici ---
    headless: bool = True
    profile_dir: str = "/data/profile"
    """Kalici Chromium profili. Cerezler/onaylar burada saklanir, volume'a baglayin."""
    pool_size: int = 1
    """Es zamanli sayfa (sekme) sayisi. Google rate-limit'i sert, 1-2'de tutun."""
    browser_args: List[str] = []

    # --- Arama ---
    google_domain: str = "www.google.com"
    hl: str = "tr"
    """Arayuz dili."""
    gl: str = "TR"
    """Ulke kodu."""
    locale: str = "tr-TR"
    timezone: str = "Europe/Istanbul"
    user_agent: Optional[str] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    mobile_user_agent: str = (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
    )

    # --- Onbellek / hiz ---
    cache_ttl: float = 900.0
    """Ayni sorgu icin sonucun taze sayilacagi sure (saniye). 0 = onbellek kapali."""
    cache_max_entries: int = 500
    batch_delay: float = 2.5
    """Toplu sorguda istekler arasi bekleme (saniye). Google rate-limit'i icin dusurmeyin."""
    max_batch_size: int = 50

    # --- Zamanlama (saniye) ---
    nav_timeout: float = 45.0
    """Sayfa yuklenmesi icin ust sinir."""
    answer_timeout: float = 90.0
    """AI cevabinin akmasi bitene kadar beklenecek ust sinir."""
    stable_for: float = 1.6
    """Metin bu kadar sure degismezse akis bitmis sayilir."""
    poll_interval: float = 0.4

    # --- Cerez onayi ---
    auto_consent: bool = True
    consent_choice: str = "reject"
    """'reject' (varsayilan, gizlilik dostu) veya 'accept'."""

    # --- Ayiklama ---
    answer_selectors: List[str] = [
        'div[data-subtree="aimc"]',
        'div[data-async-context] div[data-subtree]',
        "#im-box",
        'div[jsname="txFAF"]',
    ]
    """Google DOM'u degistiginde GAM_ANSWER_SELECTORS ile JSON liste olarak ezilebilir.
    Hicbiri tutmazsa en buyuk metin blogu heuristigine dusulur."""


@lru_cache
def get_settings() -> Settings:
    return Settings()
