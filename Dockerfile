FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    libsndfile1-dev \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads transcriptions models

# Set environment variables
ENV PYTHONPATH=/app
ENV HF_HOME=/app/models
ENV HF_HUB_CACHE=/app/models
ENV HF_HUB_DISABLE_SYMLINKS_WARNING=true

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["python", "-m", "app.main"]