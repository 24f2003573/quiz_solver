FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

# Install Python deps (do NOT install playwright again)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of your app
COPY . .

# Render will set PORT; default to 8000 for local
ENV PORT=8000

CMD ["python", "main.py"]
