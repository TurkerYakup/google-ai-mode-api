FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    GAM_PROFILE_DIR=/data/profile

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates tzdata fonts-liberation fonts-noto-core fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Kullaniciyi kaynak kodundan ONCE olustur: boylece uygulama degistiginde sadece
# asagidaki kucuk COPY katmanlari yeniden kurulur. /ms-playwright'i chown'lamiyoruz;
# tarayici dosyalari zaten herkes tarafindan okunabilir ve o katman ~500 MB.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/profile \
    && chown -R app:app /data /srv

COPY --chown=app:app app ./app
COPY --chown=app:app scripts ./scripts

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
