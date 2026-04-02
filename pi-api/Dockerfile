FROM python:3.11-slim

WORKDIR /app

# Install docker CLI so the container can spawn sandbox sibling containers
RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# PI_EXECUTE_TOKEN must be passed at runtime via --env
# Docker socket must be mounted at runtime: -v /var/run/docker.sock:/var/run/docker.sock
CMD ["python", "app.py"]
