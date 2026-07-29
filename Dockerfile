# Odysseus — production image.
#
# Railway's autodetect found Python, pip installed requirements, and guessed a
# start command. It could not know that the ASGI app lives in app.py rather
# than main.py, that the frontend needs a Node build first, or that OCR needs a
# system binary pip cannot provide. A Dockerfile settles all three.

# ---------------------------------------------------------------------------
# Stage 1: build the React frontend. Node is not needed at runtime, so it stays
# in this stage and never reaches the final image.

FROM node:20-slim AS frontend
WORKDIR /build
COPY Frontend/package.json Frontend/package-lock.json ./
RUN npm ci
COPY Frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: the Python runtime.

FROM python:3.12-slim

# tesseract is a binary, not a pip package. Without it every scanned PDF and
# every junk-text-layer page fails extraction, while native PDFs keep working,
# so the failure looks like a data problem rather than a missing dependency.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements first, so a code change does not invalidate the pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /build/dist ./Frontend/dist

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Shell form so ${PORT} expands. Railway injects its own port at runtime.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
