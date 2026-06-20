FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FALCONSCAN_OCR_ENABLED=true
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user
EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
