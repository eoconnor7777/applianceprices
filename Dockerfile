# Run the tracker with no local Python - only Docker Desktop required.
#   docker build -t prices .
#   docker run --rm -v "%cd%/data:/app/data" prices     (PowerShell: ${PWD})
# Then open data/report.html
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -m playwright install chromium
COPY . .
CMD ["sh", "-c", "python -m appliance_price_tracker.cli track && python -m appliance_price_tracker.cli report --out data/report.html"]
