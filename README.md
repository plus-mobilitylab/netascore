# Bikeability Index

This project is a collection of tools that (TODO).
Please write the following points:
- What is the general purpose
- Do you have specifics that can be listed here?
- What does it do? (e.g. it takes XYZ... and as a result UVW comes out...)
- What are the goals of this Project (very important)
- What are the non-goals of this Project (very important!!!)
- TODO: answer all of the above points

This project uses the following technologies:
- python 3
- PostgreSQL with PostGIS extension
- Docker (optional)
- psql
- ogr2ogr
- osm2pgsql
- raster2pgsql

## Workflow

The workflow is specified in a settings file in YAML (`.yml`) format.
The settings file contains information about:
- how to connect to the database
- which parameters to use in the process
- what datasets to import
- how and where to export the results

The settings file itself does not contain geodata, it merely points to the files to be used.
The format of the settings file is specified in ![settings.md](settings-spec.md).

The system relies on a PostgreSQL database and a Python script that is executed.
The database can be
- on the local machine
- on the local machine in a Docker container (scripts and information on how to run the db in a docker container are included in this project)
- on a remote machine

The python script can either be executed directly, or run in a Docker container. For the Docker specific part see [docker.md](docker.md).

Internally, the process consists of the following steps:

1. import_step
2. optional_step
3. network_step
4. attributes_step
5. index_step
6. export_step

### 1. import_step

In this step a network dataset is imported, currently `gip` and `osm` are supported, resulting in various database tables with the prefix `gip_` or `osm_`.

`gip`
- The necessary sub-datasets are extracted from the ZIP files of the OGD dataset, as defined in the settings file.
- The extracted TXT files are parsed to CSV and SQL files, containing the raw data and `create table` statements.
- The database tables are imported from the SQL, CSV, GPKG files, primary keys are added, attributes are cleaned. The geometry is not transformed.

`osm`
- The necessary database tables are imported from a PBF file, as defined in the settings file. The geometry is not transformed.
- Additionally, the optional datasets `building`, `crossing`, `facility`, `greenness`, `water` are derived as database tables. The geometry is transformed.

### 2. optional_step

In this step optional datasets are imported, currently `dem`, `noise`, `building`, `crossing`, `facility`, `greenness`, `water` are supported, resulting in identically named database tables.

`dem`
- A database raster table is imported from a GeoTIFF file, as defined in the settings file. The raster is not transformed.
- The SRID needs to be defined in the settings file.

`noise`, `building`, `crossing`, `facility`, `greenness`, `water`
- A database table is imported from a geopackage file. The geometry is transformed.

### 3. network_step

In this step the final network dataset is created, resulting in the database tables: `network_edge`, `network_node`.

`gip`
- Different sub-datasets are merged.
- The network dataset is reduced to necessary edges.
- The network dataset is reduced to necessary attributes.
- The geometry is transformed.

`osm`
- The network dataset is reduced to necessary edges.
- The network dataset is reduced to necessary attributes.
- The geometry is transformed.
- The intersections are corrected, considering tunnels and bridges.
- The indoor edges are corrected.
- A unique edge ID is created.

### 4. attributes_step

In this step necessary [attributes / indicators](attributes.md) for routing applications and the index calculation are derived from the final network dataset and optional datasets, resulting in the database tables: `network_edge_attributes`, `network_node_attributes`, `network_edge_export`.
- Attributes are derived: `access_*`, `bridge`, `tunnel`
- Indicators for the index calculation are derived into predefined value domains so that the resulting values are comparable regardless of the source dataset.
- Indicators that can not be derived, because of missing datasets or attributes, are set to NULL.
- The table `network_edge_export` is created with a standardized table scheme independently of the source dataset.

### 5. index_step

In this step indices will be calculated based on the weight profiles defined in the settings file, resulting in the tables: `network_edge_index`, `edge`, `node`.
- The index is calculated as a weighted average over all available indicators for every edge.
  - The values of the indicators are rated with predefined values between 0 (best) and 1 (worst) for the respective use-cases (bike or walk).
  - The indicators are weighted with values between 0 (best) and 1 (worst) as defined in the weights file.
- The tables `edge` and `node` are created by joining the resulting datasets from the previous steps, including all attributes, indicators and indices.

### 6. export_step

In this step the tables `edge` and `node` are exported, as defined in the settings file.

`geopackage`
- The tables `edge` and `node` are exported to a geopackage with identically named layers.

## How to run the project

This sections describes how to run the project directly on your machine. For information on how to run it in a Docker environment see [docker.md](docker.md).

Make sure that you have a local PostgreSQL database running and specified the correct database credentials in the settings file.

Copy the input and optional datasets, the settings file and all weights files to a folder named "data" in the root of the repository.

Install the software dependencies:

- PostgreSQL with PostGIS extension
- psql
- ogr2ogr
- osm2pgsql
- raster2pgsql

Install the Python dependencies for this project with:

    RUN pip install -r requirements.txt

Then run the pipeline by providing the filename of the settings file to the script:

    generate_index.py your-settings-file.yml

The processing of the files can take several minutes up to several hours - depending on the size of the geodata and the hardware used.

Example settings files that can be used and adapted to your needs can be found in the `settings/examples` folder.

If you want to re-run the pipeline, but skip certain steps, use the `--skip` flag with a list of steps you want to skip:
`import`, `network`, `attributes`, `optional`, `index`, `export` (the steps are explained in detail below)

e.g.

    generate_index.py your-settings-file.yml --skip import network attributes

If you want to get more detailed log outputs, set the `--loglevel` flag to one of the following levels: 
`1` = MajorInfo, `2` = Info (default), `3` = Detailed, `4` = Debug

## Comparison of running the pipeline in Docker and directly on the machine

One advantage of running everything in Docker is that you do not have to install the dependencies on your machine. Only docker is required.
On the other hand, running the pipeline in Docker is potentially slower on macOS and Windows than running it directly on the machine.

If you run the pipeline directly on the machine, you have to make sure that all dependencies are met and the correct python version is used (you can use a virtual environment for that).

## How to contribute

TODO: please provide information where to best start out when someone new wants to change or extend something.

The entrypoint of execution is the file `generate_index.py`. This script parses the arguments and verifies that all settings are correct and no mandatory parts are missing.
Then it runs several steps in order and calls the respective handlers for that step.

TODO:
- important next steps
- future possibilities

TODO: how do you handle contributions? Should people send in pull requests?

## Limitations

TODO: what are the projects limitations and shortcomings

- Results depend on input data quality
- GeoPackages are to be provided in required format

## Credits

TODO
- university which provided the project and some historical details about it: University of Salzburg, Department of Geoinformatics
- developers: Dana Kaziyeva, Petra Stutz, Martin, Christian, Robin
- sponsors (credits go out to trafficon for ...): City of Salzburg, FFG
  - We are thankful for funding in different research projects: FFG, City of Salzburg
- used tutorials or helpful websites?
- misc/other helpers?
- open source providing "funded by trafficon"
- 

## License

This project is published with the MIT license. For details please see [LICENSE](LICENSE)
