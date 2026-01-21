# Base image with Python
FROM python:3.11-slim

# Install system deps and Chromium + driver
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        chromium chromium-driver \
        wget curl unzip gnupg ca-certificates fonts-liberation \
        libnss3 libxss1 libasound2 libatk-bridge2.0-0 libgtk-3-0 libgbm1 && \
    rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/lib/chromium/chromedriver \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app

WORKDIR /app

COPY requirements.txt requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Streamlit listens on 8501 by default
EXPOSE 8501

CMD ["streamlit", "run", "apps/streamlit/app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
