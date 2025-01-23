FROM python:3.10-slim

WORKDIR /app

# Systemabhängigkeiten installieren
RUN apt-get update && \
    apt-get install -y ffmpeg build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
