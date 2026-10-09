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
        ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    python3 -m venv --system-site-packages /opt/netascore

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python", "./generate_index.py"]
