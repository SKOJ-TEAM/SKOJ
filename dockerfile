FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

RUN apt-get -o Acquire::Retries=5 \
       -o Acquire::http::Timeout=30 update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) \
       -exec sed -i 's|http://|https://|g' {} + \
    && apt-get -o Acquire::Retries=5 \
       -o Acquire::https::Timeout=30 update \
    && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-dev \
    python3.10-venv \
    python3-pip \
    build-essential \
    git \
    pkg-config \
    libmariadb-dev \
    libxml2-dev \
    libxslt1-dev \
    libssl-dev \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblua5.3-dev \
    gettext \
    nodejs \
    npm \
    libimage-exiftool-perl \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN python3.10 -m venv /opt/venv

COPY site/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir gunicorn==23.0.0

WORKDIR /app/site

COPY site /app/site
COPY site/dmoj/settings.example.py /app/site/dmoj/settings.py
COPY docker/django/local_settings.py /app/site/dmoj/local_settings.py
COPY docker/django/entrypoint.sh /usr/local/bin/skoj-entrypoint

RUN chmod +x /usr/local/bin/skoj-entrypoint \
    && mkdir -p /app/site/tmp/static /problems

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/skoj-entrypoint"]
CMD ["gunicorn", "dmoj.wsgi:application", "--bind", "0.0.0.0:8000"]
