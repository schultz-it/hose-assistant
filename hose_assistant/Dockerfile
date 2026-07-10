ARG BUILD_FROM
FROM $BUILD_FROM

# tzdata: resolves named zones (e.g. Europe/Rome) for both the container's
# TZ env var (see rootfs run script) and Python's zoneinfo (core/sun.py).
RUN apk add --no-cache python3 py3-pip tzdata

WORKDIR /app
COPY backend/requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY backend/ /app/backend/
COPY frontend/dist/ /app/frontend/dist/
COPY rootfs /

RUN chmod a+x /etc/services.d/hose_assistant/run
