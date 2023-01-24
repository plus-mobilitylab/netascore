# Running the project in docker containers

This section describes how to run all components or only parts in docker.
You need two components:

1. a postgis database (you can use any standard image)
2. the bikeability script (or docker image)

NOTE: passwords and usernames are only used for simplicity reasons. Please use secure usernames and passwords in production!

# Use the docker image provided on Docker Hub

There is no need to build the docker image yourself - you may simply get the latest version of the image using

```bash
docker pull plusmobilitylab/netascore:latest
```

To run the workflow with an existing postgres database, simply follow these steps:

- create a directory named `data` and place all geofiles inside
- add weights files and settings file to this directory (see example files provided in the code repository)
- adjust settings to your needs in the `settings.yml` file
- finally, execute the workflow using:

```bash
docker run -v <dir_to_data_directory>:/usr/src/netascore/data plusmobilitylab/netascore data/settings.yml
```

# All components run in docker

For a full docker pipeline, there are no other prerequisites than a working docker installation.

If you don't use an official image, then you can build the image for yourself:

```bash
docker build -t bikeability .
```

This builds a local docker image named `bikeability`.

Now create a network (required only once per computer):

```bash
docker network create bikeability-net 
```

Start the postgis database and attach it to the network:

```bash
docker run --name bikeability-db --network=bikeability-net \
        -e POSTGRES_PASSWORD=postgres -d postgis/postgis:13-3.2
```

```bash
# Map TCP port 5432 in the container to port 5433 on the Docker host:
docker run --name bikeability-db --network=bikeability-net -p 5433:5432 \
        -e POSTGRES_PASSWORD=postgres -d postgis/postgis:13-3.2
```

Make sure that the database connection in your `settings.yml` is set up for docker:

```yml
database:
    host: bikeability-db
    port: 5432
    dbname: postgres
    username: postgres
    password: postgres
```

Make sure that you have all needed geofiles and settings and weight files in one subdirectory, because this directory is
mounted into the bikeability container:

```bash
# linux and mac:
docker run -t --network=bikeability-net \
        -v $(pwd)/data:/usr/src/netascore/data bikeability data/settings.yml
```

```shell
# windows:
docker run -t --network=bikeability-net \
        -v %cd%/data:/usr/src/netascore/data bikeability data/settings.yml
``` 

## Only the database runs in docker

If the database runs in docker, then you have to configure your database to accept connections from the local machine:

```bash
docker run --name bikeability-db --network=bikeability-net -p 5432:5432 \
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

If the script runs inside the docker container, it needs access to the database outside of the docker ecosystem.
If the external database runs on another host, provide the necessary connection information in the `database` section.

If you have the database running on your local system, then the host needs the ip of the local system. Please note, that
`127.0.0.1` will not work, because it would try to connect to the local container. If you are unable to obtain the ip of your
machine, or you cannot establish a connection, use `gateway.docker.internal` as the host, e.g.:

```yml
database:
  host: gateway.docker.internal
  port: 5432
  dbname: postgres
  username: postgres
  password: postgres
```

## Limitations

When using bikeability in a docker image on mac or windows, the performance of the pipeline is low and can take 3-5 times longer when using bikeability in a docker container due to slow docker volume mounts.
If you experience performance problems, either run the python script directly, or copy the files into the container:

```bash
docker volume create bikeability-storage

docker create -t --network=bikeability-net --name bikeability-pipe \
        -v bikeability-storage:/usr/src/netascore/data bikeability data/settings.yml

docker cp data/. bikeability-pipe:/usr/src/netascore/data

docker start bikeability-pipe
```

To monitor the progress (logs), run:

```bash
docker logs -f bikeability-pipe
```

This command will show the logs of the container and will follow the logs. You can stop the command with `ctrl+c`.

To copy the resulting files back to your local system, you can use the following command:

```bash
docker copy bikeability-pipe:/usr/src/netascore/data/YOUR_GEO_RESULT_FILE1.gpkg .
docker copy bikeability-pipe:/usr/src/netascore/data/YOUR_GEO_RESULT_FILE2.gpkg .
```

# Overwrite `default.style`

By default, this file is provided within the docker container. To overwrite some settings perform the following steps:

- copy the file from this repository
- modify the settings you need to modify
- mount the settings file into the docker container when running it

```bash
# linux and mac:
docker run -t --network=bikeability-net \
        -v $(pwd)/default.style:/usr/src/netascore/resources/default.style \
        -v $(pwd)/data:/usr/src/netascore/data bikeability data/settings.yml
```

```shell
# windows:
docker run -t --network=bikeability-net \
        -v %cd%/default.style:/usr/src/netascore/resources/default.style \
        -v %cd%/data:/usr/src/netascore/data bikeability data/settings.yml
``` 
