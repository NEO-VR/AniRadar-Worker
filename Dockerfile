# Use Python 3.12 (based on your local .pyc files)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies first (for better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Create directories for database and sessions (Telethon needs this)
RUN mkdir -p /app/db /app/sessions

# Run the bot as a module (since src has __init__.py)
CMD ["python", "-m", "src.bot"]
