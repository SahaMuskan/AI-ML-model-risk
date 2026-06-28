FROM python:3.12-slim

WORKDIR /app

# Install deps first so this layer is cached on code-only changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# data/ is created at runtime (and git-ignored — the COPY above won't include it)
RUN mkdir -p data

EXPOSE 8000

# Uvicorn bound to 0.0.0.0 so it's reachable from outside the container.
# Set workers > 1 only after moving to a production database (SQLite has one-writer limits).
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
