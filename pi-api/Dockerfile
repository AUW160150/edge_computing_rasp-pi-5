FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# PI_EXECUTE_TOKEN must be passed at runtime via --env or docker-compose
CMD ["python", "app.py"]
