# Changelog

Notable changes since [1.1.1](https://github.com/plus-mobilitylab/netascore/compare/v1.1.1...dev-main).

## [2.0.0]

### Added

- Place name, bounding box, and geofile (`aoi_filename`) as OSM download areas. Place names are now resolved with Nominatim for better results.
- UTM zone of the area centroid when `target_srid` is omitted for those downloads.
- OSM network clipping to the area of interest (import setting `clip`: `bbox` (default), `aoi`, or `none`). Also available for OSM file imports when `place_name`, `bbox`, or `aoi_filename` is given. Only the relevant part of the OSM data is imported (requires osmium).
- Parking indicator (`allowed`, `implicit`, `forbidden`).
- Bicycle infrastructure class `bicycle_road` for bicycle roads with motor traffic.
- Sights indicator for applications in tourism with an exemplary mode profile `profile_bike_tourism.yml`.
- GIP 2.0 import (`type: gip2`).
- Optional GIP source attributes in the export (`include_source_attributes`).
- Conda environment `netascore` (`environment.yml`, Python 3.13).

### Changed

- Refined OSM values for bicycle infrastructure, pedestrian infrastructure, road category, and pavement - updated to match current OSM conventions.
- Omitted `buffer` means no buffer (previously 500 m).
- `water` is a ratio from 0 to 100 (previously `true` or `false`).
- Ratios of `facilities`, `crossings`, and `sights` are now counts per area (ha) surrounding an edge (previously per 100 m of edge length). 
- Bicycle roads with car access are categorized as road category `calmed`. Without car access they are classified as `no_mit` (no motorized traffic) and bicycle infrastructure `bicycle_way` or `mixed_way`. 
- `edge_id` is derived from the OSM way id and the segment position. This simplifies segment-level comparison across separate execution runs of NetAScore
- Docker database image `postgis/postgis:18-3.6`.
- Dependencies: jinjasql2 replaces JinjaSql. Flask, igraph, and pandas are no longer required.
- Settings and profile files require `version: 2.0`.

### Fixed

- Frequently failing Overpass API download requests.
- OSM tag lookups for cycle-route scope, bicycle roads, unhewn cobblestone, and `sidewalk:right` / `sidewalk:both`.
- Revised OSM max speed defaults. 
- Noise re-import no longer duplicates values.
- Settings paths may contain a backslash.
- Missing input files report a readable error.
- Several minor bugs fixed.

### Removed

- Place-name filters `admin_level` and `zip_code`. Please use more precise `place_name`values instead - e.g. "Oberndorf, Salzburg, Österreich". You may check via openstreetmap.org (using Nominatim)
- Directional parking columns `parking_ft` and `parking_tf`.
