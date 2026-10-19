# One image for both Railway backend services.
#
# API service command (default):
#   uvicorn app.main:app --host 0.0.0.0 --port $PORT
#
# LiveKit worker command (set as an override in Railway):
#   python -m app.interview.agent start
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . ./

# Railway provides PORT at runtime. The fallback makes local container testing
# convenient without changing production behavior.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
