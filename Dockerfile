FROM python:3.10-slim

WORKDIR /app

# Systemabhängigkeiten installieren
RUN apt-get update && \
    apt-get install -y ffmpeg build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Abhängigkeiten installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Den gesamten Code kopieren
COPY . .

# Starte den Bot im Modulmodus – so wird src als Paket erkannt.
CMD ["python", "-m", "src.bot"]