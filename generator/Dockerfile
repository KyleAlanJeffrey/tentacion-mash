# Generator container — native Python + Pillow + OpenCV (no WASM limits).
# Built and pushed automatically by `npx wrangler deploy` (context: repo root).
FROM python:3.12-slim

WORKDIR /app
COPY generator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY celebs.txt .
COPY generator/ generator/

EXPOSE 8080
CMD ["python", "generator/server.py"]
