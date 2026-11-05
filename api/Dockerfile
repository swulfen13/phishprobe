# PhishProbe orchestrator. Holds the Vultr Inference key (never the sandbox),
# runs the quick check + agent loop + verdict engine, and launches/destroys
# sandbox containers via the mounted Docker socket.
FROM python:3.12-slim

WORKDIR /app

# docker CLI is not required — we use the docker SDK over the socket.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
