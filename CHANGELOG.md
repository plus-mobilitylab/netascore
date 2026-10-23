# Changelog

Changes since release [1.1.1](https://github.com/plus-mobilitylab/netascore/compare/v1.1.1...dev-main).

## [2.0.0]

### Added

- Place name, bounding box, and geofile (`aoi_filename`) as OSM download areas. Place names are now resolved with Nominatim for better results.
- Overpass API downloads are limited to areas up to 1500 km² (import setting `max_download_area`). Larger areas require an OSM extract (e.g. from Geofabrik).
- UTM zone of the area centroid when `target_srid` is omitted for those downloads.
- The UTM zone of a case created with an OSM file is now determined as mean position of imported ways if neither `target_srid` nor an area of interest are given and stored in the AOI table.
- OSM network clipping to the area of interest (import setting `clip`: `bbox` (default), `aoi`, or `none`). Also available for OSM file imports when `place_name`, `bbox`, or `aoi_filename` is given. Only the relevant part of the OSM data is imported (requires osmium).
- Parking indicator (`allowed`, `implicit`, `forbidden`), computed for OSM and GIP. In version 1.x, parking columns were placeholders. Mode profiles from 1.x need to map the new values.
- Bicycle infrastructure class `bicycle_road` for bicycle roads with motor traffic.
- Sights indicator for applications in tourism with an exemplary mode profile `profile_bike_tourism.yml`.
- For Austria: new GIP 2.0 import (`type: gip2`).
- Option to add source attributes to the export (`include_source_attributes`): either `True` for a predefined set of columns, or a list of column names / OSM tag keys. (exported with prefix `gip_` / `osm_`).
- Import for noise data with custom column name (optional setting `column_noise`, default `noise`), non-numeric values (optional `value_mapping` to numeric values), and several layers (setting `layer`, required if the file contains more than one geometry layer).
- Dataset registry for shared datasets (optional imports and datasets derived from OSM): source, import settings, coordinate system, and covered area are recorded. Existing datasets are only reused if they match the current import settings (when using the option `on_existing: reuse`), or imported again (`reuse_or_overwrite`). Optional imports accept the additional property `coverage` (polygons of the covered area).
- The attributes step checks input datasets against the imported network: datasets covering only parts of the network result in no indicator value (NULL) for edges outside their coverage (reflected in the index robustness), datasets not covering the network are not used, and datasets in a different coordinate system are transformed (each with a warning or info).
- Metadata in the output GeoPackage: `meta_run` (NetAScore version, settings as YAML without passwords, input file incl. OSM data timestamp, processing steps of the last run incl. completion time, run duration), `meta_steps` (per processing step: time, duration, version, and settings of the run in which it was executed last), `meta_datasets` (input datasets: use, share of the network covered, origin), `meta_profiles` (mode profiles: original content of the profile files, SHA-256 checksum, weights), and `meta_areas` (AOI, clip area, network extent, coverage of the input datasets). A summary of the run is printed at the end.
- Code state of NetAScore in the console output and the metadata (`netascore_commit` in `meta_run` and `meta_steps`): branch and Git commit (`-dirty` for uncommitted changes), or for Docker images the build argument `NETASCORE_COMMIT`.
- Layer styles in the output GeoPackage, applied by default when a layer is opened in QGIS: for the `edge` layer one style per mode profile showing its index (higher value of both directions; the style of the first profile is the default), and for further layers (e.g. `meta_areas`).
- Conda environment `netascore` (`environment.yml`, Python 3.13) incl. osm2pgsql, osmium, and the GDAL tools - only `raster2pgsql` (for DEM imports) needs to come from a PostGIS installation.

### Changed

- Refined OSM values for bicycle infrastructure, pedestrian infrastructure, road category, and pavement - updated to match current OSM conventions.
- Omitted `buffer` means no buffer (previously 500 m).
- Walk profile: the value override for sidewalks along primary and secondary roads is removed. Sidewalks get consistent `pedestrian_infrastructure` values across all road types.
- Improved detection logic of OSM pedestrian access.
- Ratios of `facilities`, `crossings`, and `sights` are now counts per area (ha) surrounding an edge (previously per 100 m of edge length). 
- `water` is a ratio from 0 to 100 (previously `true` or `false`).
- `gradient` (`gradient_ft` / `gradient_tf`) now is the gradient in % (positive: uphill; previously: classes from -4 to 4). Example mode profiles reproduce the previously used classes. For OSM, node elevations are now interpolated bilinearly from the DEM to reduce unrealistic gradients for short edges.
- Bicycle roads with car access are categorized as road category `calmed`. Without car access they are classified as `no_mit` (no motorized traffic) and bicycle infrastructure `bicycle_way` or `mixed_way`. 
- `edge_id` is derived from the OSM way id and the segment position. This simplifies segment-level comparison across separate execution runs of NetAScore
- Processing steps (network, attributes, index, export) always replace previous outputs in the database; `on_existing` in the `database` section is no longer used (use the command line option `--skip` to skip steps).
- Setting `on_existing` uses the values `reuse`, `reuse_or_overwrite`, `overwrite`, and `abort` (previously `skip`, `delete`, `abort`). The old values are still accepted (`skip` corresponds to `reuse`).
- Processing order: optional imports now run after the network step (import, network, optional, attributes, index, export). Optional data (vector data and DEM) is only imported for the extent of the network (incl. 50 m margin), unless `clip: none` is set for the respective optional import.
- Optional OSM import (for Austrian GIP data): the OSM file is clipped to the network extent by default, like other optional datasets (setting `clip`: `network`).
- GIP import setting `filename_A` is renamed to `filename` (for consistency with OSM file imports).
- `designated_route` is now derived directly from the membership of OSM ways in bicycle route relations, per direction (previously: geometric overlap with the route). Proposed routes (`state=proposed`) are not regarded. For GIP imports, routes still apply to both directions of a link (as included in GIP input data).
- OSM import uses the flex output of osm2pgsql (the pgsql output is deprecated). After updating, run the import step again for existing OSM data.
- Example settings files harmonized: each example has its own `case_id` and exports to `netascore_<case_id>.gpkg`; the OSM download example now uses `on_existing: reuse_or_overwrite`; all available settings are documented in the examples; the development examples now use  OSM download and run without further settings.
- Docker image based on `debian:trixie` with Python 3.13 (previously `python:3.8.17-bullseye`).
- Docker database image `postgis/postgis:18-3.6`.
- Dependencies: jinjasql2 replaces JinjaSql. New: geopandas (>= 1.0), geopy, and osmium (osmium-tool, for clipping the OSM data); osm2pgsql 1.9 or newer is required (for flex output). Flask, igraph, pandas, requests, and osm2geojson are no longer required.
- Settings and profile files require `version: 2.0`.

### Fixed

- OSM network: improved split logic to catch all edge intersections. Some cases of self-touching edges or several pairs intersecting at the same point were missed in previous versions. Edge ids of the affected ways change after applying this fix.
- OSM `oneway` values now interpreted more consistently. Previously, some cases might have been mis-classified regarding one-way direction applied.
- OSM tag interpretation of `motorcar` fixed. 
- OSM steps (`highway=steps`) never allow car or bicycle access, even with explicit permissions set.
- Fixed conversion of OSM `width` values without a number (e.g. `m`) and accepting values with decimal comma.
- Changed AOI settings (`place_name`, `bbox`, `aoi_filename`) are no longer ignored when re-running a case with `reuse` setting: the AOI records the settings it was created from and is only reused if they match (with `reuse_or_overwrite` it is created again, incl. a new UTM zone if `target_srid` is omitted; with `reuse` an error is reported). For `bbox` and `aoi_filename`, the geometry is compared as well.
- Removing a defined area of interest from import settings now processes the whole file again when re-run (no more cached AOI clipping from previous settings).
- An existing OSM download is only reused if it covers the area of interest. OSM downloads now contain their bounding box. A provided OSM file covering only parts of the area (by bbox) results in a warning.
- Ensure that a re-run starting with the attributes step does not use OSM data imported for another case in the meantime. The network step stores the bicycle route memberships of the network in the case schema, so the following steps do not depend on shared OSM tables.
- The OSM import checks input OSM file and conflicts with existing datasets derived from OSM (with `on_existing: reuse` or `abort`) before shared OSM tables are replaced.
- Datasets derived from OSM (e.g. `building`, `parking`) are only reused if they cover the current import area (added spatial check).
- Running the network step with `--skip import` after changing `buffer` or `clip` reports an error if the imported OSM data does not cover the new clip area (previously, edges at the boundary were missing).
- The AOI exported in `meta_areas` is the one the network is based on (stored by the network step), not the current entry of the shared AOI table.
- `parking`: edges with equal overlap of several parking values get the value by fixed priority (`allowed`, `implicit`, `forbidden`) - previously it depended on the order of the data, so results could differ between runs.
- A `case_id` longer than 40 characters is reported with a readable error.
- Frequently failing Overpass API download requests.
- Failed Overpass API requests are reported with the HTTP status or error (also at log level 1), incl. errors the Overpass API reports within the response (e.g. query timeout or out of memory - incomplete data) and truncated responses. If all endpoints fail, a hint explains how to use a downloaded OSM extract instead. Incomplete downloads are deleted, so they are not re-used by the next run.
- Reusing an existing AOI (`on_existing: reuse` / `reuse_or_overwrite`) no longer skips the OSM download: if no download file exists (e.g. because a previous run failed before or during the download), the OSM data is downloaded for the existing AOI.
- OSM tag lookups for cycle-route scope, bicycle roads, unhewn cobblestone, and `sidewalk:right` / `sidewalk:both`.
- Revised OSM max speed defaults. 
- `water`: only line geometries (no polygons) in input data are now properly considered - previously resulted in value 0.
- Noise re-import no longer duplicates values.
- Fixed noise indicator for GIP data (Austria): edges within noise data coverage but outside any polygon are assigned numeric 0 instead of NULL (same logic as for OSM).
- Settings paths may contain a backslash.
- Settings files given without directory (e.g. `python generate_index.py settings.yml`): mode profiles were not found.
- Database passwords and file names with special characters no longer break the import or export.
- Missing input files report a readable error.
- DEM import now reports errors of `raster2pgsql`.
- DEM import with `raster2pgsql` from outside the conda environment (e.g. system PostGIS): the GDAL plugins of the conda environment are no longer loaded to prevent errors.
- For GIP imports, a DEM given in the optional section is no longer imported and a warning is issued (gradients are computed from the elevation data contained in the GIP dataset, as before).
- For OSM imports, an OSM file given in the optional section is no longer imported and a note is issued.
- AOI files (`aoi_filename`) in other coordinate systems than WGS84 are now transformed. AOI files without coordinate reference system report an error.
- GeoPackage imports skip empty geometries (which could crash the PostGIS backend) and tables without geometry (e.g. QGIS layer styles).
- Without `target_srid`, all steps use the SRID determined for the AOI of the case, also when the import step is skipped (previously fell back to EPSG:32633).
- Settings and mode profiles: missing or empty sections (e.g. `database`, `optional`) and missing keys no longer cause crashes. Mode profiles are validated when loading, indicators without a weight are not regarded in index computation, and unknown keys (e.g. typos) in settings files and mode profiles are reported as warnings. `bbox` accepts a list or a comma-separated string for OSM and GIP imports.
- Console output: more compact, fixed timestamp issues, internal messages only at detailed log level (`--loglevel 3` or `4`). GDAL errors now raise exceptions (no more FutureWarning of GDAL). Database connection errors are properly reported also at default log level.
- Several minor bugs fixed.

### Removed

- Place-name filters `admin_level` and `zip_code`. Please use more precise `place_name` values instead - e.g. "Oberndorf, Salzburg, Österreich". You may check via openstreetmap.org (using Nominatim)
- Directional parking columns `parking_ft` and `parking_tf` (unused).
- osm2pgsql style file `resources/default.style` (pgsql output) - replaced by the flex configuration `resources/osm2pgsql_flex.lua`. Custom styles need to be adapted.
- Documentation files `attributes.md`, `docker.md`, and `settings.md` - now the documentation is available at https://plus-mobilitylab.github.io/netascore-documentation/
