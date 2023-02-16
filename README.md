# NetAScore - Network Assessment Score Toolbox for Sustainable Mobility

NetAScore provides a toolset and automated workflow for computing ***bikeability***, ***walkability*** and related indicators from publicly available network data sets. Currently, we provide common presets for assessing infrastructure suitability for cycling (*bikeability*) and walking (*walkability*). By editing settings files and mode profiles, additional modes or custom preferences can easily be modeled.

For global coverage, we support **OpenStreetMap** data as input. Additionally, Austrian authoritative data, the **'GIP'**, can be used if you work on an area of interest within Austria. 

## How to get started?/

To get a better impression of what this toolset and workflow provides, you can quickly start with processing a sample area.

### Easy quickstart: ready-made Docker image

The easiest way to get started is running the ready-made Docker image. All you need for this to succeed is a [Docker installation](https://docs.docker.com/engine/install/) and internet connection. Then, follow these two steps:

- download the `docker-compose.yml` file from the `examples` ([file link](https://raw.githubusercontent.com/plus-mobilitylab/netascore/main/examples/docker-compose.yml)) to an empty directory
- from within this directory, execute the following command from a terminal:
  `docker compose run netascore`

Docker will download the NetAScore image and PostgreSQL database image, setup the environment for you and finally execute the workflow for Salzburg, Austria as an example case.

#### What it does (example case):

NetAScore first loads an area of interest by place name from Overpass Turbo API, then downloads the respective OpenStreetMap data and afterwards imports, processes and exports the final dataset. A new subdirectory named `data` will be present after successful execution. Within this folder, the assessed network is stored in `netascore_salzburg.gpkg`. It includes *bikeability* in columns `index_bike_ft` and `index_bike_tf` and *walkability* in `index_walk_ft` and `index_walk_tf`. The extensions `ft` and `tf` refer to the direction along an edge: *from-to* or *to-from* node. These values represent the assessed suitability of a segment for cycling (*bikeability*) and walking (*walkability*).

#### What the results look like:

Currently, NetAScore does not come with a built-in visualization module. However, you can easily visualize the *bikeability* and *walkability* index by loading the geopackage in [QGIS](https://qgis.org). Simply drag and drop the geopackage into a new QGIS project and select the `edge` layer. Then in layer preferences define a symbology that visualizes one of the computed index values - e.g. `index_bike_ft` for *bikeability* (`_ft`: bikeability in forward-direction of each segment).

This is an exemplary visualization of *bikeability* for Salzburg, Austria:

![Bikeability result for Salzburg, Austria](https://user-images.githubusercontent.com/24413180/216041815-9e2457e5-ce2f-48b3-9df4-5c33f805de38.png)

#### How to proceed?

Most likely, you want to execute an analysis for a specific area of your interest - please see the [instructions in Docker.md](docker.md) for how to achieve this with just changing one line in the settings file.

### Running NetAScore locally (without Docker)

For running NetAScore without Docker you need several software packages and Python libraries installed on your machine. You find all details in the section "How to run the project".

**NetAScore uses the following technologies:**

- python 3
- PostgreSQL with PostGIS extension
- Docker (optional)
- psql
- ogr2ogr
- osm2pgsql
- raster2pgsql

## What is NetAScore?

TODO: what does it do? -> inputs, outputs,...

#### Goals and Roadmap

TODO: add

#### Non-Goals

TODO: to be defined...



## The workflow

NetAScore uses six steps for generating *bikeability* and *walkability* indicators from network data and optional auxillary data sets. For each step, parameters can be defined for applying the generic workflow to a specific use case. These parameters are defined in a settings file in YAML (`.yml`) format.

The settings file contains information about:

- how to connect to the database
- which parameters to use in the process
- what datasets to import
- how and where to export the results
- global settings such as SRID (spatial reference system)

The settings file itself does not contain geodata. It specifies all parameters such as which input files to be used. You find details on which options are available and what they mean in [settings.md](settings.md). In general, each step of the workflow has its respective section in the settings file. NetAScore also comes with a set of examplary settings files in the `examples` subdirectory.

The system relies on a PostgreSQL database and a Python script that is executed.

The database can be

- stand-alone on the local machine
- provided in a Docker container (see [docker.md](docker.md) for details)
- on a remote machine

The python script can either be executed directly, or run in a Docker container. For the Docker specific part see [docker.md](docker.md).

**The NetAScore workflow consists of the following steps:**

1. import_step
2. optional_step
3. network_step
4. attributes_step
5. index_step
6. export_step

In the following subsections, we explain these individual steps.

### 1. import_step

In this step a network dataset is imported. Currently `osm` (OpenStreetMap) and `gip` (Austrian authoritative dataset) are supported, resulting in several database tables with the prefix `osm_` or `gip_`.

`osm`

- The necessary database tables are imported from a PBF or XML file, as defined in the settings file. The geometry is not transformed - this will be done in the network_step.
- Additionally, the optional datasets `building`, `crossing`, `facility`, `greenness`, `water` are derived as database tables. The geometry is transformed.

`gip`

- The necessary sub-datasets are extracted from the ZIP files of the OGD dataset, as defined in the settings file.
- The extracted TXT files are parsed to CSV and SQL files, containing the raw data and `create table` statements.
- The database tables are imported from the SQL, CSV, GPKG files, primary keys are added, attributes are cleaned. The geometry is not transformed.

### 2. optional_step

In this step optional datasets are imported. Currently `dem`, `noise`, `building`, `crossing`, `facility`, `greenness` and `water` are supported, resulting in identically named database tables.

`dem`
- A database raster table is created from a GeoTIFF file representing surface elevation, as defined in the settings file. Raster reprojection is not necessary. Projections are handled in the `attributes` step.
- The SRID of the input file needs to be defined in the settings file.
- **Please note:** DEM input is not considered for **GIP**-based workflow, as elevation data is already provided with the network dataset.

`noise`, `building`, `crossing`, `facility`, `greenness`, `water`
- A respective database table is generated from each geopackage file. The geometry is transformed.

### 3. network_step

In this step the final network dataset is created, resulting in the database tables: `network_edge`, `network_node`.

`osm`
- The network dataset is reduced to necessary edges.
- The network dataset is reduced to necessary attributes.
- The geometry is transformed.
- The intersections are corrected, considering tunnels and bridges.
- The indoor edges are corrected.
- A new, unique edge ID is created in addition to original `osm_id`.

`gip`

- Different sub-datasets are merged.
- The network dataset is reduced to necessary edges.
- The network dataset is reduced to necessary attributes.
- The geometry is transformed.

### 4. attributes_step

In this step, necessary [attributes / indicators](attributes.md) for routing applications and the index calculation are derived from the final network dataset and optional datasets, resulting in the database tables: `network_edge_attributes`, `network_node_attributes`, `network_edge_export`.
- Attributes are derived: `access_*`, `bridge`, `tunnel`
- Indicators for the index calculation are derived into predefined value domains so that the resulting values are comparable regardless of the source dataset.
- Indicators that can not be derived, because of missing datasets or attributes, are set to NULL.
- The table `network_edge_export` is created with a standardized table scheme independent of the source dataset.

### 5. index_step

In this step indices will be calculated based on the weight profiles defined in the settings file, resulting in the tables: `network_edge_index`, `edge`, `node`.
- The index is calculated as a weighted average over all available indicators for every edge.
  - The values of the indicators are rated with predefined values between 0 (best) and 1 (worst) for the respective use cases (bike or walk).
  - The indicators are weighted with values between 0 (best) and 1 (worst) as defined in the weights file.
- The tables `edge` and `node` are created by joining the resulting datasets from the previous steps, including all attributes, indicators and indices.

### 6. export_step

In this step the tables `edge` and `node` are exported, as defined in the settings file.

`geopackage`
- The tables `edge` and `node` are exported to one geopackage with the layers `edge` and `node`.

## How to run the project

This sections describes how to run the project directly on your machine without Docker. For information on how to run it in a Docker environment see [docker.md](docker.md). However, for a **quick start**, we recommend to use the **ready-made Docker image** as outlined in "How to get started".

In order to run NetAScore, you need to prepare a **`data` directory** that contains at least the **settings file** and **weights files** for *bike* and *walk* profiles. You find **example files** in the `examples` subdirectory of the NetAScore repository. If available, also copy the input data sets and optional data sets to the `data` subdirectory in your repository root.

As a next step, make sure that you have a (local) **PostgreSQL** database running and that you specified the correct database connection details in the settings file. 

Please find more information on possible options available in the **settings file** and their meaning in [settings.md](settings.md).

Make sure you have installed these **software dependencies**:

- Python 3.x
- recent PostgreSQL with PostGIS extension
- psql
- ogr2ogr
- osm2pgsql
- raster2pgsql

Then, install the **Python dependencies** for this project - e.g. with pip:

    RUN pip install -r requirements.txt

Now you can **run NetAScore** by providing the filename of the settings file as commandline parameter to the Python script:

    generate_index.py your-settings-file.yml

The processing can take several minutes up to several hours - depending on the size of the geodata and the hardware used. Therefore, we recommend to start with a small example first.

### Additional commandline parameters

If you want to re-run the pipeline, but **skip certain steps**, use the **`--skip`** flag with a list of steps you want to skip:  `import`, `network`, `attributes`, `optional`, `index`, `export` (the steps are explained in detail in this readme file). In the following example, `import`, `network` and `attributes` steps will be skipped and only the `export` step is re-executed:

    generate_index.py your-settings-file.yml --skip import network attributes

If you want to get more (or less) detailed **log outputs**, set the **`--loglevel`** flag to one of the following levels: 
`1` = MajorInfo, `2` = Info (default), `3` = Detailed, `4` = Debug

## Running NetAScore in Docker or better directly on the machine in Python?

The great advantage of running NetAScore in Docker is that you do not have to install any software or python dependencies on your machine. Only docker is required. Also the configuration is very simple, as you get a ready-to-use setup including a PostgreSQL database with PostGIS extension.

However, running NetAScore in Docker can potentially be slower on macOS and Windows than running it directly on the machine in Python. We provide a possible solution to this issue in [docker.md](docker.md) - the performance can be optimized by using a different way to mount the Docker volume. If you prefer to execute NetAScore directly on your machine, virtual environments or Conda may help with managing all Python requirements.

## How to contribute

We are happy about contributions, feedback and ideas that help developing NetAScore further.

If you want to work with the source code of NetAScore, you might want to start exploring it from the entrypoint of execution in `generate_index.py`. This script parses all arguments and settings and verifies their correctness and that all mandatory information is given. Then it runs all processing steps in order and calls the respective handlers for each step.

TODO:
- important next steps
- future possibilities

TODO: how to handle contributions? Should people send in pull requests?

## Limitations

TODO: what are the projects limitations and shortcomings

- Results depend on input data quality
- GeoPackages are to be provided in required format

## Credits

NetAScore is developed by the [Mobility Lab](https://mobilitylab.zgis.at/) at the Department of Geoinformatics (Z_GIS), University of Salzburg, Austria.

The main developers are: Dana Kaziyeva, Martin Loidl, Petra Stutz, Robin Wendel and Christian Werner.

As NetAScore relies on great OpenSource software, we want to thank all contributors to these projects - especially PostgreSQL with PostGIS and OSGeo4W.

We want to thank [TraffiCon GmbH](https://www.trafficon.eu/) and [Triply GmbH](https://triply.net/) for contracted research and development. Research on the concepts of *bikeability* and *walkability* as well as the development of the NetAScore software was made possible by [SINUS](https://projekte.ffg.at/projekt/3325243) (BMK, FFG No. 874070), [POSITIM](https://projekte.ffg.at/projekt/3298537) (BMK, FFG No. 873353) and On-Demand II (BMK & BMAW, FFG No. 880996).

## License

This project is licensed under the MIT license. For details please see [LICENSE](LICENSE)
