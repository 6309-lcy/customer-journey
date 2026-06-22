# Use a slim Python image
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY static/ ./static/

# Create data directory (will be mounted as volume in production)
RUN mkdir -p /app/data/uploads /app/data/processed

# Default environment
ENV DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

# Expose the port
EXPOSE 8000

# Use uvicorn for production (single worker is fine for this use case)
# For higher load you can use gunicorn + uvicorn workers
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]