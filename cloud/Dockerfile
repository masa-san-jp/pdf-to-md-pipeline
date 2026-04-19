FROM python:3.11-slim

WORKDIR /app
COPY cloud/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cloud/ ./cloud/
CMD ["python", "-m", "cloud.main"]
