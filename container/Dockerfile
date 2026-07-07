# Generator container — native Python + Pillow + OpenCV (no WASM limits).
# Built and pushed automatically by `npx wrangler deploy`.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watcher.py splice.py celebs.txt ./
COPY container/server.py .

EXPOSE 8080
CMD ["python", "server.py"]
