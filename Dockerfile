# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies (if any, e.g., for database connectors or image processing)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
# --no-cache-dir saves space, consider --upgrade if needed
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
# This copies everything, consider adding a .dockerignore file in backend/
# to exclude venv, .git, etc.
COPY . /app/

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
# Using 0.0.0.0 makes the server accessible externally within the Docker network
# Add migrations step if you want it to run automatically on start
# CMD python manage.py migrate && python manage.py runserver 0.0.0.0:8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"] 