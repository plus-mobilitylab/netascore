FROM python:3.8.17-bullseye AS buildstage

WORKDIR /usr/src/netascore

# COPY generate_index.py .
COPY *.py ./
COPY core core/
COPY resources resources/
COPY sql sql/
COPY toolbox toolbox/
COPY examples examples/
# COPY settings settings/
COPY requirements.txt .

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && \
    apt install -y \
    gdal-bin \
    libgdal-dev \
    postgresql-client-common \
    postgresql-client-13 \
    osm2pgsql && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT [ "python", "./generate_index.py" ]