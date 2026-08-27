ARG JAVA17_IMAGE=eclipse-temurin:17-jdk
ARG DMOJ_RUNTIMES_IMAGE=dmoj/runtimes-tier1:latest

FROM ${JAVA17_IMAGE} AS java17

FROM ${DMOJ_RUNTIMES_IMAGE}

ARG DMOJ_JUDGE_COMMIT=5ef74c5d6cad9efb2e86a5bb8ff2c90aaa6e435c

COPY --from=java17 /opt/java/openjdk /usr/lib/jvm/java-17-openjdk-amd64

RUN ln -sf /usr/lib/jvm/java-17-openjdk-amd64/bin/java /usr/local/bin/java \
    && ln -sf /usr/lib/jvm/java-17-openjdk-amd64/bin/javac /usr/local/bin/javac \
    && find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) \
       -exec sed -i 's|http://|https://|g' {} + \
    && apt-get -o Acquire::Retries=5 \
       -o Acquire::http::Timeout=30 \
       -o Acquire::https::Timeout=30 update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /judge /problems \
    && cd /judge \
    && git init \
    && git remote add origin https://github.com/DMOJ/judge-server.git \
    && git fetch --depth 1 origin "${DMOJ_JUDGE_COMMIT}" \
    && git checkout --detach FETCH_HEAD \
    && python3 -m venv --prompt=DMOJ /env \
    && /env/bin/pip3 install cython setuptools \
    && /env/bin/pip3 install -e . \
    && HOME=~judge . ~judge/.profile \
    && runuser -u judge -w PATH -- /env/bin/dmoj-autoconf -V \
       > /judge-runtime-paths.yml

ENTRYPOINT ["/usr/bin/tini", "--", "/judge/.docker/entry"]
