FROM ubuntu:22.04

# Python 로그를 즉시 출력하고 모든 Python 명령이 격리된 가상환경을 사용하게 합니다.
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

# 패키지 mirror 일시 장애를 재시도하고 이후 다운로드는 HTTPS로 강제합니다.
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

# 시스템 Python과 애플리케이션 의존성을 분리합니다.
RUN python3.10 -m venv /opt/venv

# requirements가 바뀌지 않으면 무거운 Python 의존성 레이어를 재사용합니다.
COPY site/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && pip install --no-cache-dir gunicorn==23.0.0

WORKDIR /app/site

# 운영 실행에 필요한 소스와 Docker 전용 설정을 이미지 안에 고정합니다.
COPY site /app/site
COPY site/dmoj/settings.example.py /app/site/dmoj/settings.py
COPY docker/django/local_settings.py /app/site/dmoj/local_settings.py
COPY docker/django/entrypoint.sh /usr/local/bin/skoj-entrypoint

# 컨테이너 시작 전 필요한 공용 디렉터리를 이미지에도 미리 준비합니다.
RUN chmod +x /usr/local/bin/skoj-entrypoint \
    && mkdir -p /app/site/tmp/static/releases /problems

# 릴리스 메타데이터를 마지막에 두어 Git SHA만 바뀔 때 운영체제·Python 의존성·소스 복사·
# 디렉터리 준비 레이어까지 무효화되지 않게 합니다.
ARG RELEASE_ID=development
# 같은 SHA를 컨테이너 환경과 OCI label에 기록해 실행 이미지 추적에 사용합니다.
ENV RELEASE_ID=${RELEASE_ID}
LABEL org.opencontainers.image.revision=${RELEASE_ID}

# Nginx에는 호스트 8001/8002로 publish되지만 컨테이너 내부 Gunicorn은 항상 8000입니다.
EXPOSE 8000

# entrypoint가 릴리스 디렉터리를 준비한 뒤 기본 Gunicorn 명령을 exec합니다.
ENTRYPOINT ["/usr/local/bin/skoj-entrypoint"]
CMD ["gunicorn", "dmoj.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "5"]
