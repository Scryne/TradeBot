FROM python:3.12-slim
RUN pip install --no-cache-dir "nautilus-trader==2.0.0rc5" numpy pandas polars pyarrow
WORKDIR /app
COPY canli.py karar.py veri.py ./
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
CMD ["python", "canli.py"]
