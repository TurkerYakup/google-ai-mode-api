FROM python:3.12-slim

WORKDIR /app

# Copy canary script and secrets
COPY check.py /app/check.py

# Create data directory for state, history, artifacts
RUN mkdir -p /data && chmod 755 /app/check.py

# Read env from mounted /run/canary/secrets.env
ENV API_BASE=http://google-ai-mode-api:8000

# Run the canary (infinite loop until docker stop)
CMD ["python", "/app/check.py"]
