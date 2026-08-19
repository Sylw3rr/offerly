# Offerly — one image, runnable anywhere that takes a container.
#
# A Dockerfile rather than a platform's own build format on purpose: whatever
# this is deployed to today, it should be movable tomorrow without rewriting
# the deployment.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Polish text passes through this application end to end; the C locale
    # would mangle it at every boundary that guesses an encoding.
    PYTHONUTF8=1 \
    PORT=8000

WORKDIR /app

# Dependencies first, so a change to the application does not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Nothing here needs to write to its own filesystem, and a process that cannot
# is one fewer thing to worry about.
RUN useradd --create-home --shell /usr/sbin/nologin offerly \
    && chown -R offerly:offerly /app
USER offerly

EXPOSE 8000

# `--proxy-headers` is not optional behind a load balancer: without it the
# application believes it is being reached over http, and every absolute URL it
# builds — the stylesheet among them — comes out as http on an https page,
# where the browser refuses to load it.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
