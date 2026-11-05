# Throwaway browser sandbox. Based on the official Playwright image so Chromium
# and all OS deps are present. The container is launched with cap_drop=ALL,
# read_only rootfs, a tmpfs /tmp, resource limits and NO secrets — see
# api/sandbox/manager.py and section 7 of CLAUDE.md.
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

# `pwuser` already exists in the base image and owns /ms-playwright.
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY runner.py .

# The rootfs is read-only at runtime; Chromium + temp files go to tmpfs /tmp.
ENV HOME=/tmp \
    TMPDIR=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    PYTHONUNBUFFERED=1

USER pwuser
EXPOSE 8080
CMD ["python", "runner.py"]
