# Use official Playwright Python image with browsers preinstalled
FROM mcr.microsoft.com/playwright/python:v1.56.0-jammy

# Set workdir
WORKDIR /app

# Copy requirements and install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of your app
COPY . .

# Render will set PORT; default to 8000 for local
ENV PORT=8000

# Start your Flask app
CMD ["python", "main.py"]
