FROM python:3.13.7-trixie AS buildstage

WORKDIR /usr/src/netascore

COPY *.py ./
COPY core core/
COPY resources resources/
COPY sql sql/
COPY toolbox toolbox/
COPY examples examples/
COPY requirements.txt .

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gdal-bin=3.10.3+dfsg-1 \
        libgdal-dev=3.10.3+dfsg-1 \
        postgresql-client-17 \
        osm2pgsql && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python", "./generate_index.py"]
