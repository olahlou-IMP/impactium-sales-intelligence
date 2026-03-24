FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p playbooks
ENV PORT=8080
EXPOSE ${PORT}
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT}
