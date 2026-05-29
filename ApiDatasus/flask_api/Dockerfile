FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código e modelos para dentro da imagem
COPY . .

EXPOSE 5001

# Default: HTTP para dev/health-check
# Em produção o docker-compose sobrescreve com: python worker.py
CMD ["python", "app.py"]
