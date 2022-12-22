# Settings file

A settings file holds the necessary information to perform all steps for creating bikeability/walkability data.
The file format is `yaml`. More information about yaml can be found on https://yaml.org/

A settings file consists of several sections. Sections are mandatory for the steps you are running.
You can omit sections if you skip all steps that need this section. E.g. if you skip the `export` step, then
you don't need to provide an `export` section.

## Structure

The basic structure is presented in this section.

Structure:

- version (mandatory. At the moment, this is always 1)
- database
- import
- optional
- weights
- export

## Section `database`

The database connection is the most basic information you need to provide, without it,
no data can be imported, transformed or exported.
If you don't provide any information, the program will start up normal,
but it will most likely abort with a connection error.

Example settings are provided and should be a good starting point for your own project.

The default settings are:

```yaml
database:
  host: bikeability-db
  port: 5432
  dbname: postgres
  username: 
  password: 
```

## Section `import`

### `type` 

Specify the type of geodata you want to import. At the moment, the following file formats
are supported:

- osm
- gip

### `filename`

The file containing the geodata.

- OSM data can be imported in the PBF format, which can be downloaded here: https://download.geofabrik.de
- GIP data can be imported from the IDF export, which can be downloaded here: https://www.data.gv.at/katalog/dataset/3fefc838-791d-4dde-975b-a4131a54e7c5

### `on_existing`

If the import steps discovers a database with already existing data it acts according to this setting.
The possible values are:

- skip (default): skip the import
- delete: delete existing data and run the import again
- abort: abort program execution with an error

### `Example import section`

```yaml
import:
  type: osm
  filename: austria-latest.osm.pbf
  filename_style: default.style
  on_existing: delete
```

## Section `optional`

This is the most flexible section and specifies data that can be optionally imported for better quality results of the index.
The following optional data can be imported:

- dem (GeoTIFF)
- noise (GeoPackage: Polygon, MultiPolygon)
- osm (PBF)

- building (GeoPackage: Polygon)
- crossing (GeoPackage: Point, LineString)
- facility (GeoPackage: Point, Polygon)
- greenness (GeoPackage: Polygon)
- water (GeoPackage: LineString, Polygon)

### Subsection `dem`

- `filename`: name of the file to be imported
- `srid`:  spatial reference system identifier (SRID) of the dataset

The DEM (digital elevation model) is used to add elevation values to the network nodes and to calculate the gradient of a road segment.
For Austria the 10 m x 10 m DEM can be downloaded here: https://www.data.gv.at/katalog/dataset/b5de6975-417b-4320-afdb-eb2a9e2a1dbf

### Subsection `noise`

- `filename`: name of the file to be imported

The noise dataset contains the mapping of noise levels in decibels.
For Austrian states the noise datasets can be downloaded here: https://www.data.gv.at/katalog/dataset/b5de6975-417b-4320-afdb-eb2a9e2a1dbf

### Subsection `osm`

- `filename`: name of the file to be imported

An OSM dataset can be used to derive the following optional datasets: `building`, `crossing`, `facility`, `greeness`, `water`

### Subsection `building`, `crossing`, `facility`, `greeness`, `water`

- `filename`: name of the file to be imported

If these datasets are not directly derived from an OSM dataset, they can be imported from other data sources.

## Section `weights`

The weights are used to determine the importance of the individual indicators. Different use cases have different weights.
We included weights for biking as well as walking. You can create custom profiles or modify existing ones.
Ideally, you do not need to change anything here. Just copy the section from the examples, or use this code:

```yaml
weights:
  -
    profile_name: bicycle
    filename: weights_bicycle.yml
  -
    profile_name: pedestrian
    filename: weights_pedestrian.yml
```

## Section `export`

At the moment, only exporting into a geopackage file is supported. Use the following code:

```yaml
export:
  type: geopackage
  filename: osm_network.gpkg 
```

