FROM debian:trixie

WORKDIR /usr/src/netascore

COPY *.py ./
COPY core core/
COPY resources resources/
COPY sql sql/
COPY toolbox toolbox/
COPY examples examples/
COPY requirements.txt .

ENV DEBIAN_FRONTEND=noninteractive
ENV VIRTUAL_ENV=/opt/netascore
ENV PATH="/opt/netascore/bin:${PATH}"
ENV PROJ_DATA=/usr/share/proj
# code state of NetAScore (logged and stored in the output metadata), e.g.:
# docker build --build-arg NETASCORE_COMMIT="$(git rev-parse --abbrev-ref HEAD), $(git describe --tags --dirty --always)" .
ARG NETASCORE_COMMIT=""
ENV NETASCORE_COMMIT=${NETASCORE_COMMIT}

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        python-is-python3 \
        gdal-bin \
        python3-gdal \
        python3-geopandas \
        python3-geopy \
        python3-psycopg2 \
        python3-yaml \
        postgresql-client \
        postgis \
        osm2pgsql \
        osmium-tool \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    python3 -m venv --system-site-packages /opt/netascore

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python", "./generate_index.py"]
