FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Run as non-root (CIS Docker 4.1). Pre-create the SQLite data dir owned by the
# app user so the mounted fra1_data volume inherits writable ownership.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
