# Settings file

NetAScore uses a settings file that holds the necessary information to perform all steps for computing *bikeability* and *walkability*. It is written in YAML markup language. General information about YAML can be found at https://yaml.org/.

We provide a set of **example settings files** with NetAScore. You find them inside the subdirectory `examples`. The most common to start from is `settings_osm_query.yml`. This is the file used by default in the Docker image. It is configured for easy use with all components running in Docker and no local input files required. See [docker.md](docker.md) for instructions on executing NetAScore in this example setup.

Settings files for NetAScore consist of several sections. For **every processing step** that should be executed, a **corresponding settings section** needs to be provided. This means that you can omit sections if you skip all processing steps that require this section. E.g. if you skip the `export` step, then you don't need to provide an `export` section.

In this document, we provide an overview on the structure of settings files and details on available settings for each processing step.

Besides the settings file, you also need to provide a mode profile file for each of the modes you want to compute a suitability index for. For now, please refer to the two mode profiles provided in the `examples/` subdirectory for reference and copy them to the `data` directory for usage in your own queries.

## Structure

The settings file can consist of the following **sections**:

- **version**: 
  mandatory, single value. For compatibility with NetAScore version 1.1, the settings file `version` entry should be `1.2`.
- **global**: 
  general settings such as target reference system (SRID) to use
- **database**: 
  connection parameters for PostgreSQL database
- **import**: 
  essential information for importing core datasets
- **optional**: 
  information on optional datasets to import
- **profiles**: 
  specification of indicator weights and indicator value mappings per mode profile - e.g. for *bikeability* and *walkability*
- **export**: 
  information for exporting results



## Section `global`

### Property `target_srid` 

**This parameter is optional if using GIP** (for the whole of Austria) **or OSM Download via place name** - in these cases NetAScore uses the centroid's UTM zone by default. However, **if working with OSM file import** (e.g. Planet OSM / Geofabrik downloads), you should **provide an appropriate reference system** for your specific area of interest.
Specify the SRID (spatial reference system as EPSG-code) to use for processing and data output. 
Datasets will be imported and if necessary transformed to this reference system. 
**Please note: currently only metric unit systems are supported such as UTM**.

**Example**:

- for WGS 84 UTM zone 33N use: 32633

### Property `case_id`

This parameter allows you to specify a unique identifier for the current task as defined in the settings file. It may be useful if working with different areas of interest, different mode profiles, or when re-executing parts of a workflow. You can include this identifier e.g. in export file names using `<case_id>` as a placeholder.

**Note**: Only alphanumeric characters [A-Z, a-z, 0-9] and '_' are allowed. Other characters will be removed.




## Section `database`

Connection details for a PostgreSQL database are required in order to import, transform,  assess and export data. If you don't provide any information, the program will start up normal, but it will most likely terminate soon after with a connection error.

Example settings are provided in the `examples` directory and should be a good starting point for customization.

The **default settings** for using the **Docker** setup (NetAScore and PostgreSQL running in containers) are:

```yaml
database:
  host: netascore-db
  port: 5432
  dbname: postgres
  username: postgres
  password: postgres
```

If you want to connect to a **local PostgreSQL instance** outside of Docker, but running NetAScore in Docker you can use the following settings:

```yaml
database:
  host: gateway.docker.internal
  port: 5432              # port of existing PostgreSQL server on localhost
  dbname: postgres        # name of target database
  username: postgres      # local postgres user
  password: postgres
  on_existing: abort 	  # skip, delete, abort
```

For using the whole toolset without Docker, just provide connection details for your PostgreSQL database as you do with any other software.

**Note**: For security reasons, you should **provide `username` and `password` as environment variables** if you do not work within a test environment. In this case just set `DB_USERNAME` and `DB_PASSWORD` accordingly and remove `username` and `password` keys from the settings file.



## Section `import`

### Property `type` 

Specify the type of geodata you want to import. At the moment, the following file formats
are supported:

- value `osm`: OpenStreetMap
- value `gip`: Austrian authoritative dataset *"Graphenintegrations-Plattform GIP"* - see also: [http://www.gip.gv.at](http://www.gip.gv.at/en/index.html)

### Property `filename`

Refers to the file containing the geodata.

- OSM data can be imported from `PBF` format, which can be downloaded e.g. from https://download.geofabrik.de. For directly downloading a small AOI with NetAScore, use one of the options outlined in the following section "Additional options for OSM".
- GIP data for Austria can be imported from the `IDF` export files which can be downloaded from [https://www.data.gv.at](https://www.data.gv.at/katalog/dataset/3fefc838-791d-4dde-975b-a4131a54e7c5)

### Additional options for OSM

NetAScore allows you to **directly download OpenStreetMap data** via Overpass API. You can simply provide the following properties instead of the `filename` property:

- property **`place_name`**: Name of a place, referring to a polygon. Typically you could use the name of a city or city district. E.g. 'Salzburg' or 'City of London'. If the place name given is not unique, you can either opt for an interactive prompt by adding the setting `interactive: True` or specify additional parameters:

  - `admin_level`: filters the given results for OSM 'admin_level' property (see [OSM documentation](https://wiki.openstreetmap.org/wiki/Item:Q1074))
  - `zip_code`: filters the given results for a ZIP code (if available in OSM data) 

  **Please note**: Network data is being queried based on the bounding box (rectangle) containing the polygon returned for the place name query. If you do not specify a reference system (global option `target_srid`), the UTM zone suitable for the centroid of the area of interest is used.

- property **`buffer`**: When using the `place_name` query, this option allows you to specify a spatial buffer to enlarge the extent of network data being queried. The unit of the buffer is defined by the target SRID - currently this must be in meters. 

- property **`bbox`**: Bounding box of your area of interest in WGS 84 (longitude and latitude, geographic coordinates) - e.g. for Salzburg (Austria) use: `bbox: 47.7957,13.0117,47.8410,13.0748`
  **Please note**: when using this option, please specify **`target_srid`** in the `global` settings section to define an appropriate spatial reference system for your custom area of interest

- properties **`include_rail`** and **`include_aerialway`**: These optional `boolean` tags allow you to include railway and aerialway features into the network dataset. This may be useful for visualization and specific types of analysis. For example, provide `include_rail: True` if you want railway geometry to be included in the output data set.
  
- (advanced) property `filename_style`: For importing OpenStreetMap data into the database, NetAScore uses [osm2pgsql](https://osm2pgsql.org/). Import settings for this commandline utility are provided in a `default.style` file. By default, NetAScore provides this file in the `resources` directory. This setting, however, allows you to specify a custom style file.


### Property `on_existing`

This setting defines how to handle file and database table conflicts during any import and processing step (e.g. when trying to re-import a file with the same `case_id`).

The possible values are:

- **`skip`** (default): skip the import
- **`delete`**: delete existing data and run the import and/or processing again (overwrites existing data)
- **`abort`**: terminate program execution (will report an error) - in this case, you are responsible to manually resolve conflicts

### Example import section

This is an example for OpenStreetMap import using a place name query:

```yaml
import:
  type: osm
  on_existing: delete
  place_name: Salzburg
  interactive: True
  buffer: 1000
```

The following example uses an existing OSM extract for Austria downloaded from https://download.geofabrik.de. It additionally specifies a custom `default.style` for OSM import to the database.

```yaml
import:
  type: osm
  filename: austria-latest.osm.pbf
  filename_style: default.style
  on_existing: delete
```



## Section `optional`

This is the most flexible section and specifies data that can optionally be imported for higher quality results of the resulting index.

The following optional data is currently supported:

- **dem** (GeoTIFF): digital elevation model
- **noise** (GeoPackage: Polygon, MultiPolygon): polygons with noise attribute (e.g. traffic noise)
- **osm** (PBF): only relevant for GIP import, if OpenStreetMap data should be used to infer the layers `building`, `crossing`, `facility`, `greenness` and `water`

The following layers can be supplied if OpenStreetMap data is not used or if you wish to use custom datasets:

- **building** (GeoPackage: Polygon)
- **crossing** (GeoPackage: Point, LineString)
- **facility** (GeoPackage: Point, Polygon)
- **greenness** (GeoPackage: Polygon)
- **water** (GeoPackage: LineString, Polygon)

### Subsection `dem`

The DEM (digital elevation model) is used to add elevation values to the network nodes and to calculate the gradient of a road segment.

- Property `filename`: name of the file (GeoTIFF) to be imported
- Property `srid`:  spatial reference system identifier (SRID) of the dataset

For Austria a 10 m x 10 m DEM can be downloaded here: [https://www.data.gv.at](https://www.data.gv.at/katalog/dataset/b5de6975-417b-4320-afdb-eb2a9e2a1dbf)

### Subsection `noise`

The noise dataset contains a mapping of noise levels in decibels, represented as polygons with associated noise attribute.

- `filename`: name of the file to be imported

For Austrian states the noise datasets can be downloaded here: [https://www.inspire.gv.at](https://geometadatensuche.inspire.gv.at/metadatensuche/srv/ger/catalog.search#/metadata/125ec87c-7120-48a7-bd2c-2718cbf878c6)

### Subsection `osm`

This is only relevant when working with GIP data as main input. An OSM dataset can be used to derive the following optional datasets: `building`, `crossing`, `facility`, `greeness`, `water`

- `filename`: name of the OSM file to be imported

### Subsections `building`, `crossing`, `facility`, `greeness`, `water`

If these datasets are not directly derived from an OSM dataset, they can be imported from individual data sets. This might be useful e.g. when working with local, authoritative data sets.

- `filename`: name of the file to be imported



## Section `profiles`

NetAScore uses weights to determine the importance of individual indicators for a specific profile such as for cycling or walking. Different use cases may have different weights. Additionally, numeric indicator values are assigned to original attribute values in the mode profiles.

We include well-tested default mode profiles for cycling as well as walking with NetAScore. For general purpose assessments we recommend to utilize these profiles by copying the respective mode profile files `profile_bike.yml` and `profile_walk.yml` from `examples` to the `data` directory and referencing them from the settings file as follows:

```yaml
profiles:
  -
    profile_name: bike
    filename: profile_bike.yml
    filter_access_bike: True
  -
    profile_name: walk
    filename: profile_walk.yml
    filter_access_walk: True
```

You may edit these profiles or create your own custom profiles and add them to this section of the settings file. The `profile_name` value is included in the column name of the resulting index: e.g. `index_bike_ft`.

Since NetAScore version 1.1.0, index values are only computed for edges with legal access per mode. This filter is indicated by `filter_access_<mode>: True`. You may include segments accessible to other modes by adding multiple lines of `filter_access_<mode>`.  Possible modes are: `bike`, `walk` and `car`. For example, if you want to compute bikeability for all segments that are accessible by bike but also for those only open to pedestrians you may use:

``````yaml
profiles:
  -
    profile_name: bike
    filename: profile_bike.yml
    filter_access_bike: True
    filter_access_walk: True
``````

For details on weight file definition and computation steps involved, please refer to the [README](README.md) and [attributes](attributes.md) documentation.



## Section `export`

Currently, NetAScore supports exporting the assessed network into a geopackage file. You can define this as follows:

```yaml
export:
  type: geopackage
  filename: osm_network.gpkg 
```

If you provide a `case_id` in the `global` settings section, you can include it in the export filename by using the placeholder `<case_id>`:

```yaml
export:
  type: geopackage
  filename: netascore_<case_id>.gpkg
```

