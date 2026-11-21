FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --user-group inventory
COPY --chown=inventory:inventory app/ app/
COPY --chown=inventory:inventory alembic.ini ./
COPY --chown=inventory:inventory migrations/ migrations/
USER inventory
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
