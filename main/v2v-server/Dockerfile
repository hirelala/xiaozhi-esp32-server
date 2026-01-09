FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8765

ENV LIVEKIT_URL=""
ENV LIVEKIT_API_KEY=""
ENV LIVEKIT_API_SECRET=""

CMD ["python", "src/main.py"]
