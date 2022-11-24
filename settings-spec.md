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
TODO: Please provide the user with information about the formats
- pbf - pbf.gz?? etc
- gip - are there certain formats/programs that work?

### `on_existing`

If the import steps discovers a database with already existing data it acts according to this setting.
The possible values are:

- skip: (default: skip the import)
- delete: delete existing data and run the import
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

This is the most flexible section and specifies data that can be optionally imported for
better quality results of the index.
The following optional data can be imported:

- dem
- noise
- building
- crossing
- facility
- greenness
- water

### Subsection `dem`

- `filename`: name of the file to be imported
- `srid`:  spatial reference system identifier (SRID) of the dataset

TODO: please describe what dem is does and how it contributes to the quality of the result.

### Subsection `noise`

TODO: please describe what noise data is, where to get it and how it contributes to
the quality of the result

## Section `weights`

TODO: please specify what weights are and how they influence the imports.

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

