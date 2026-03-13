FROM python:3.11-slim-bookworm

# System dependencies for OpenCV, rclone, and camera support
RUN apt-get update && apt-get install -y \
    rclone \
    libgl1-mesa-glx \
    libglib2.0-0 \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set up explicit timezone support if needed (defaults to UTC otherwise)
ENV TZ=UTC

WORKDIR /app

# Copy requirement list and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir opencv-python-headless

# Copy source code and scripts into the container
COPY . .

# Assume configurations will be bound via docker-compose volumes
# Run the application
CMD ["python3", "main_service.py"]
