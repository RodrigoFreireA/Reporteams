FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

RUN adduser --system --group --home /app appuser

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS:-1} --threads ${GUNICORN_THREADS:-8} --timeout ${GUNICORN_TIMEOUT:-120} app:app"]
