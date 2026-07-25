# Build context is the REPO ROOT (not ./backend) so the image can copy both the
# app code and the demo dataset under backend/data. docker-compose sets this.
FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# App code + demo fixtures.
COPY backend/ ./

# Defaults to demo mode: the image runs with no secrets and no network calls.
ENV DEMO_MODE=true
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
