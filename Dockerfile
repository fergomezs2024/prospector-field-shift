# Prospector: API (FastAPI) + web client in one image.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PROSPECTOR_CACHE=/data/cache PROSPECTOR_DATOS=/data/mundo PORT=8790

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# rasterio's bundled GDAL needs libexpat, which the slim image does not ship
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*

COPY prospector ./prospector
# Compile the terrain routines (numba) once at build time; otherwise every start takes about a minute
ENV NUMBA_CACHE_DIR=/opt/numba
RUN python -c "import prospector.api" && chmod -R a+rwX /opt/numba
RUN useradd --create-home --uid 10001 prospector \
    && mkdir -p /data/cache /data/mundo && chown -R prospector /data
USER prospector
VOLUME ["/data"]
EXPOSE 8790

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/salud'%os.environ.get('PORT','8790'),timeout=4)"

# One worker on purpose: analysis jobs are tracked in memory (see docs/DEPLOYMENT.md).
CMD ["sh", "-c", "exec uvicorn prospector.api:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers"]
