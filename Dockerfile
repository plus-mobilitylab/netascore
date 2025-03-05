FROM python:3.13.2-bookworm AS buildstage

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
RUN echo "deb http://deb.debian.org/debian sid main" > /etc/apt/sources.list.d/sid.list && \
    apt update && \
    apt install -y -t sid \
    gdal-bin \
    libgdal-dev \
    libgdal36 && \
    apt install -y \
    postgresql-client-17 \
    osm2pgsql && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT [ "python", "./generate_index.py" ]
