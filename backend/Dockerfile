FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /repo/backend

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY data /repo/data

RUN chmod +x /repo/backend/start.sh

EXPOSE 8000

CMD ["/repo/backend/start.sh"]
