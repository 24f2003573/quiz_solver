FROM python:3.10-slim

# Install system dependencies needed by Playwright / Chromium
RUN apt-get update && apt-get install -y \
    wget gnupg libglib2.0-0 libnss3 libx11-6 libatk-bridge2.0-0 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 \
    libgtk-3-0 libxshmfence1 libxkbcommon0 libxfixes3 libxext6 libdrm2 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies (without playwright for now)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Install Playwright and Chromium browsers
RUN pip install playwright && python -m playwright install chromium

# Copy the rest of the app
COPY . .

# Render injects PORT; default 8000 for local
ENV PORT=8000

CMD ["python", "main.py"]
