FROM python:3.13-slim
RUN pip install --no-cache-dir b2==4.3.2
WORKDIR /app
COPY app.py index.html ./
ENV HOST=0.0.0.0 PORT=8080 CONFIG_DIR=/config DATA_ROOT=/data PYTHONUNBUFFERED=1
VOLUME /config
EXPOSE 8080
CMD ["python", "app.py"]
