FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --shell /bin/false graphone && chown -R graphone:graphone /app
USER graphone
EXPOSE 8000
CMD ["uvicorn", "graphone.main:app", "--host", "0.0.0.0", "--port", "8000"]

