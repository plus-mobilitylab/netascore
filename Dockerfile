FROM python:3.8 AS buildstage

WORKDIR /usr/src/bikeability

# COPY generate_index.py .
COPY *.py ./
COPY core core/
COPY resources resources/
COPY sql sql/
COPY toolbox toolbox/
# COPY settings settings/
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && \
    apt install -y \
    gdal-bin \
    postgresql-client-common \
    postgresql-client-13 \
    osm2pgsql && \
    rm -rf /var/lib/apt/lists/*

ENTRYPOINT [ "python", "./generate_index.py" ]