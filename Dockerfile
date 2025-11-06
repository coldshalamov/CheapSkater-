FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=0

RUN apt-get update \ 
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-liberation \
        libnss3 \
        libasound2 \
        libx11-6 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgtk-3-0 \
        libgbm1 \
        libcups2 \
        libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

RUN python -m playwright install --with-deps chromium

CMD ["python", "-m", "app.main", "--once"]
# To run in scheduled mode instead, override the command with: python -m app.main
