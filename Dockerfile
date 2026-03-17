FROM python:3.12-slim

WORKDIR /app

COPY server.py .

ENV WORKSPACE=/workspace
EXPOSE 8766

CMD ["python3", "server.py", "--port", "8766", "--workspace", "/workspace"]
