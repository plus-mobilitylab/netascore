# Running NetAScore in Docker

In this file, we describe how to run all components or only parts in Docker.
There are two components involved:

1. NetAScore (Python source or docker image)
2. a PostGIS-enabled database (which is also provided as docker image)

## Quickstart

NetAScore comes with a `docker compose` configuration in `docker-compose.yml` and a demo configuration, so you can simply run an example workflow by following these two steps (if you don't have Docker installed yet, please [install the Docker Engine](https://docs.docker.com/engine/install/) first):

- download the `docker-compose.yml` file from the `examples` directory ([file link](https://raw.githubusercontent.com/plus-mobilitylab/netascore/main/examples/docker-compose.yml)) to an empty directory
- from within this directory, execute the following command from a terminal:
  `docker compose run netascore`

NetAScore first loads an area of interest from Overpass Turbo API, then downloads the respective OpenStreetMap data and afterwards imports, processes and exports the final dataset. A new subdirectory named `data` will be present after successful execution. Within this folder, the assessed network is stored in `netascore_salzburg.gpkg`. It includes *bikeability* in columns `index_bike_ft` and `index_bike_tf` and *walkability* in `index_walk_ft` and `index_walk_tf`. The extensions `ft` and `tf` refer to the direction along an edge: *from-to* or *to-from* node.

## Run NetAScore for your own area of interest

The easiest way to run a network assessment for your own area of interest is by adapting the given example in `examples/settings_osm_query.yml`:

- create a new **subdirectory** named **`data`** (if you already ran the quickstart example, you can just use the `data` directory created)
- download the **settings template** [from here](https://raw.githubusercontent.com/plus-mobilitylab/netascore/main/examples/settings_osm_query.yml) or copy it from `examples/settings_osm_query.yml`
- add the **mode profiles** for *bikeability* and *walkability* to the `data` direcotry: copy both, `profile_bike.yml` and `profile_walk.yml` from the `examples` folder.
- **edit** your newly created **settings file** `settings_osm_query.yml` - e.g. to download data for the City of London:
  - provide a **`case_id`**  in `global` section (only alphanumeric characters are allowed - please avoid special characters such as German "Umlaute" etc.; this will be added e.g. to the output file name) - e.g. `case_id: london`
  - specify a **`place_name`** that is used to query data from OSM in the section `import`: e.g. `place_name: City of London` (please note: currently, this must equal the OSM "name" tag of your target area - you may check this using e.g. www.openstreetmap.org)
  - for editing this file we recommend using a code editor such as Visual Studio Code, Notepad++ or comparable which handles text encodings properly
- **run NetAScore** by executing the following line from a terminal inside the main directory (parent of `data`):
  `docker compose run netascore data/settings_osm_query.yml`
  (here, the last argument represents the settings file to use)

## Add more detail

The example settings use OpenStreetMap data as the only input. While this gives a good first estimate of *bikeability* and *walkability*, utilizing additional input datasets can further improve the quality of results. NetAScore supports additional datasets such as *DEM* (digital elevation model) and *noise* (e.g. traffic noise corridors). Please refer to the [settings documentation](settings.md) for details.

To add optional input data sets, follow these steps:

- acquire the file(s) for your area of interest - availability of DEM, noise map, etc. may largely depend on the area of interest
- add the file(s) to the `data` subdirectory (where the settings file and mode profiles are located)
- edit the settings file to add the new datasets and store it inside the `data` folder
- execute NetAScore from the parent directory:
  `docker compose run netascore data/<your_settings_file>.yml` (where `<your_settings_file>` refers to the file name you chose for the edited settings file)

## Manual use of the Docker image

If you want to use the NetAScore Docker image without docker compose or in a custom setting, you may simply get the latest version of the NetAScore image using:

```bash
docker pull plusmobilitylab/netascore:latest
```

To run the workflow with an existing postgres database, simply follow these steps:

- create a directory named `data` and place all geofiles inside
- add mode profile files and settings file to this directory (see example files provided in the code repository)
- adjust settings to your needs in the `settings.yml` file - see the [settings documentation](settings.md) for reference
- finally, execute the workflow using:

```bash
docker run -i -t -v <dir_to_data_directory>:/usr/src/netascore/data plusmobilitylab/netascore data/settings.yml
```

# Build the Docker image from source

The easiest way to build and launch NetAScore is by using docker compose. The `docker-compose.yml` inside the main code directory is configured accordingly. Therefore, the only command you need to execute should be:

`docker compose build`

Then, once you are sure that all input datasets, settings and mode profile files are properly placed inside the `data` subdirectory, execute NetAScore:

`docker compose run netascore data/<your_settings_file>.yml`

## The manual, stepwise approach

You can build the Docker image yourself from source using the following command from within the main code directory:

`docker build -t netascore .`

This builds a local docker image named `netascore`.

To manually create a network for communication between NetAScore and the PostgreSQL database running in Docker execute the following (required only once per computer):

`docker network create netascore-net`

Then, to run the workflow, first start the PostgreSQL database and attach it to the network:

```bash
docker run --name netascore-db --network=netascore-net \
        -e POSTGRES_PASSWORD=postgres -d postgis/postgis:13-3.2
```

```bash
# Map TCP port 5432 in the container to port 5433 on the Docker host:
docker run --name netascore-db --network=netascore-net -p 5433:5432 \
        -e POSTGRES_PASSWORD=postgres -d postgis/postgis:13-3.2
```

Make sure that the database connection in your `settings.yml` is set up to use the Docker network:

```yml
database:
    host: netascore-db
    port: 5432
    dbname: postgres
    username: postgres
    password: postgres
```

Make sure that you have all necessary geofiles, settings and mode profile files in the `data` subdirectory, because this directory is mounted into the netascore container:

```bash
# linux and mac:
docker run -i -t --network=netascore-net \
        -v $(pwd)/data:/usr/src/netascore/data netascore data/settings.yml
```

```shell
# windows:
docker run -i -t --network=netascore-net \
        -v %cd%/data:/usr/src/netascore/data netascore data/settings.yml
```



# Advanced configuration

## Only the database runs in docker

If the database runs in docker, then you have to configure your database to accept connections from the local machine:

```bash
docker run --name netascore-db --network=netascore-net -p 5432:5432 \
        -e POSTGRES_PASSWORD=postgres -d postgis/postgis:13-3.2
```

Your `database` section in the settings file should point to the local port which is mapped to the database on localhost:

```yml
database:
  host: localhost
  port: 5432
  dbname: postgres
  username: postgres
  password: postgres
```

Now you can use the python script as described in the [README.md](README.md).

## Only the script runs in docker

If the script runs inside the docker container, it needs access to the database outside of the docker ecosystem. If the external database runs on another host, provide the necessary connection information in the `database` section. If you have the database running on your local system, then the host needs the IP address or hostname of the local system. Please note that `127.0.0.1` or `localhost` will not work, because it would try to connect to the container's localhost. If you are unable to obtain the ip of your
machine, or you cannot establish a connection, use `gateway.docker.internal` as the host, e.g.:

```yml
database:
  host: gateway.docker.internal
  port: 5432
  dbname: postgres
  username: postgres
  password: postgres
```

## Troubleshooting and performance improvement

### Performance when running NetAScore in Docker

When using NetAScore in a docker image on mac or windows, overall performance of the pipeline can be 3-5 times slower compared to executing NetAScore in local Python or in Docker on Linux. This is caused by slow docker volume mounts and might be an issue for computations on large input files. 
To resolve this issue, you can either execute the python script on your machine (outside Docker) or copy the files into a volume using the following steps:

```bash
docker volume create netascore-storage

docker create -t --network=netascore-net --name netascore-pipe \
        -v netascore-storage:/usr/src/netascore/data netascore data/settings.yml

docker cp data/. netascore-pipe:/usr/src/netascore/data

docker start netascore-pipe
```

To monitor the progress (logs), run:

```bash
docker logs -f netascore-pipe
```

This command will show the logs of the container and will follow the logs. You can stop the command with `ctrl+c`.

To copy the resulting files back to your local system, you can use the following command:

```bash
docker copy netascore-pipe:/usr/src/netascore/data/YOUR_RESULT_FILE1.gpkg .
docker copy netascore-pipe:/usr/src/netascore/data/YOUR_RESULT_FILE2.gpkg .
```

### Memory issues with large datasets

In case you experience errors when processing large datasets, please make sure that you have enough memory and disk space available. 
Furthermore, it might be necessary to dedicate more memory to the database container. This can be done by adding the following line to `docker-compose.yml` within the section `netascore-db` (adjust the amount of memory to your needs):

```yml
shm_size: 2gb
```

Then, the `netascore-db`-section of `docker-compose.yml` should look like this:

```yml
netascore-db:
    image: postgis/postgis:13-3.2
    shm_size: 2gb
    ports:
    - "5433:5432"
    environment:
    - POSTGRES_USER=postgres
    - POSTGRES_PASSWORD=postgres
    - POSTGRES_DB=postgres
    healthcheck:
      test: ["CMD-SHELL", "pg_isready", "-U", "postgres"]
      interval: 10s
      timeout: 20s
      retries: 120
```


## Overwrite `default.style` for OSM import to database

For importing OpenStreetMap data into the database, NetAScore uses [osm2pgsql](https://osm2pgsql.org/). Import settings for this commandline utility are provided in a `default.style` file. By default, NetAScore provides this file within its Docker container. In order to customize `default.style` settings you may perform the following steps:

- copy the file from this repository (`resources/default.style`)
- adapt the settings according to your needs
- mount the settings file into the docker container when running it

```bash
# linux and mac:
docker run -i -t --network=netascore-net \
        -v $(pwd)/default.style:/usr/src/netascore/resources/default.style \
        -v $(pwd)/data:/usr/src/netascore/data netascore data/settings.yml
```

```shell
# windows:
docker run -i -t --network=netascore-net \
        -v %cd%/default.style:/usr/src/netascore/resources/default.style \
        -v %cd%/data:/usr/src/netascore/data netascore data/settings.yml
```
