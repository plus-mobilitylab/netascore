# NetAScore - Network Assessment Score Toolbox for Sustainable Mobility

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://github.com/plus-mobilitylab/netascore/assets/82904077/762dc210-1ca5-4ead-8aeb-522e974a93fe">
  <source media="(prefers-color-scheme: light)" srcset="https://github.com/plus-mobilitylab/netascore/assets/82904077/240d09f8-a728-41ec-b0e7-8bba8fac4d38">
  <img alt="Shows the NetAScore logo, either with light or dark background depending on the Users settings." src="https://github.com/plus-mobilitylab/netascore/assets/82904077/240d09f8-a728-41ec-b0e7-8bba8fac4d38">
</picture>



NetAScore provides a toolset and automated workflow for computing ***bikeability***, ***walkability*** and related indicators from publicly available network data sets. Currently, we provide common presets for assessing infrastructure suitability for cycling (*bikeability*) and walking (*walkability*). By editing settings files and mode profiles, additional modes or custom preferences can easily be modeled.

For global coverage, we support **OpenStreetMap** data as input. Additionally, Austrian authoritative data, the **'GIP'**, can be used if you work on an area of interest within Austria. 

For citing NetAScore, please refer to following paper which introduces the software, its objectives, as well as the data and methods used: 
Werner, C., Wendel, R., Kaziyeva, D., Stutz, P., van der Meer, L., Effertz, L., Zagel, B., & Loidl, M. (2024). NetAScore: An open and extendible software for segment-scale bikeability and walkability. *Environment and Planning B: Urban Analytics and City Science*, 0(0). [https://doi.org/10.1177/23998083241293177]. In case you want to refer to a specific version of the software implementation, you may add the respective Zenodo reference [doi.org/10.5281/zenodo.7695369](https://doi.org/10.5281/zenodo.7695369)

Details regarding the **bikeability assessment method** as well as results of an **evaluation study** are provided in the following **scientific publication**, which is openly available via [doi.org/10.1016/j.jcmr.2024.100040](https://doi.org/10.1016/j.jcmr.2024.100040): Werner, C., van der Meer, L., Kaziyeva, D., Stutz, P., Wendel, R., & Loidl, M. (2024). Bikeability of road segments: An open, adjustable and extendible model. *Journal of Cycling and Micromobility Research*, *2*, 100040.

Details on the **walkability index** together with results from a large **evaluation study** are published Open Access: [doi.org/10.3390/su17083634](https://doi.org/10.3390/su17083634): Stutz, P., Kaziyeva, D., Traun, C., Werner, C. & Loidl, M. (2025). Walkability at Street Level: An Indicator-Based Assessment Model. *Sustainability*, *17(8)*, 3634.

**Examples:** You find example output files of NetAScore at [doi.org/10.5281/zenodo.10886961](https://doi.org/10.5281/zenodo.10886961).

You find **more information** on NetAScore in the **[wiki](https://github.com/plus-mobilitylab/netascore/wiki)**:

* [About NetAScore](https://github.com/plus-mobilitylab/netascore/wiki)
* [Quickstart-guide](https://github.com/plus-mobilitylab/netascore/wiki/Quickstart%E2%80%90Guide)
* [The Workflow](https://github.com/plus-mobilitylab/netascore/wiki/The-workflow)
* [How to run the Project...](https://github.com/plus-mobilitylab/netascore/wiki/How-to-run-the-project)
  * [...in a Docker environment](https://github.com/plus-mobilitylab/netascore/wiki/How-to-run-the-project-in-a-Docker-environment)
  * [...directly on your Machine (Python)](https://github.com/plus-mobilitylab/netascore/wiki/Run-NetAScore-manually-with-Python)
* [Attributes & Indicators](https://github.com/plus-mobilitylab/netascore/wiki/Attributes-and-Indicators)
  * [Attribute derivation from OSM](https://github.com/plus-mobilitylab/netascore/wiki/Attribute-derivation-from-OSM)
  * [Attribute derivation from GIP](https://github.com/plus-mobilitylab/netascore/wiki/Attribute-derivation-from-GIP)
* [Configuration of the Settings](https://github.com/plus-mobilitylab/netascore/wiki/Configuration-of-the-settings)
* [Contribute to the Project!](https://github.com/plus-mobilitylab/netascore/wiki/How-to-contribute)
* [Requirements and Limitations](https://github.com/plus-mobilitylab/netascore/wiki/Requirements-and-Limitations)
* [Credits and License](https://github.com/plus-mobilitylab/netascore/wiki/Credits-and-license)

## How to get started?

To get a better impression of what this toolset and workflow provides, you can quickly start with processing a sample area.

### Easy quickstart: ready-made Docker image

The easiest way to get started is running the ready-made Docker image. All you need for this to succeed is a [Docker installation](https://docs.docker.com/engine/install/), running Docker Desktop and internet connection. Then, follow these two steps:

- download the `docker-compose.yml` file from the `examples` ([ download the raw file](https://github.com/plus-mobilitylab/netascore/blob/main/examples/docker-compose.yml)) to an empty directory
- from within this directory, execute the following command from a terminal:
  `docker compose run netascore`

Docker will download the NetAScore image and PostgreSQL database image, setup the environment for you and finally execute the workflow for Salzburg, Austria as an example case.

#### What it does (example case):

NetAScore first loads an area of interest by place name from Overpass Turbo API, then downloads the respective OpenStreetMap data and afterwards imports, processes and exports the final dataset. A new subdirectory named `data` will be present after successful execution. Within this folder, the assessed network is stored in `netascore_salzburg.gpkg`. It includes *bikeability* in columns `index_bike_ft` and `index_bike_tf` and *walkability* in `index_walk_ft` and `index_walk_tf`. The extensions `ft` and `tf` refer to the direction along an edge: *from-to* or *to-from* node. These values represent the assessed suitability of a segment for cycling (*bikeability*) and walking (*walkability*).

#### What the results look like:

Currently, NetAScore does not come with a built-in visualization module. However, you can easily visualize the *bikeability* and *walkability* index by loading the resulting geopackage in [QGIS](https://qgis.org). Simply drag and drop the geopackage into a new QGIS project and select the `edge` layer. Then in layer preferences define a symbology that visualizes one of the computed index values - e.g. `index_bike_ft` for *bikeability* (`_ft`: bikeability in forward-direction of each segment). Please note that from version 1.0 onwards, an index value of `0` refers to unsuitable infrastructure, whereas `1` represents well suited infrastructure.

This is an exemplary visualization of *bikeability* for Salzburg, Austria:

![Bikeability result for Salzburg, Austria](https://user-images.githubusercontent.com/24413180/229191339-7271e4ac-5a9b-4c12-ad02-dd3909215623.png)

#### How to proceed?

Most likely, you want to execute an analysis for a specific area of your interest - please see the [instructions in the wiki](https://github.com/plus-mobilitylab/netascore/wiki/How-to-run-the-project-in-a-Docker-environment#run-netascore-for-your-own-area-of-interest) for how to achieve this with just changing one line in the settings file.
If you need more detailled instructions or want to know more about the project, please consolidate the [wiki](https://github.com/plus-mobilitylab/netascore/wiki).

### Running NetAScore locally (without Docker)

For running NetAScore without Docker you need several software packages and Python libraries installed on your machine. You find all details in the section ["How to run the project"](https://github.com/plus-mobilitylab/netascore/wiki/How-to-run-the-project).

**NetAScore uses the following technologies:**

- python 3
- PostgreSQL with PostGIS extension
- Docker (optional)
- psql
- ogr2ogr
- osm2pgsql
- raster2pgsql
- [several python libraries](../main/requirements.txt)
