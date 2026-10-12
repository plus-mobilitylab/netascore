# Changelog

Notable changes since [1.1.1](https://github.com/plus-mobilitylab/netascore/compare/v1.1.1...dev-main).

## [2.0.0]

### Added

- Place name, bounding box, and geofile (`aoi_filename`) as OSM download areas. Place names are resolved with Nominatim.
- UTM zone of the area centroid when `target_srid` is omitted for those downloads.
- Parking indicator (`allowed`, `implicit`, `forbidden`).
- Sights indicator.
- Mode profile `profile_bike_tourism.yml`.
- GIP 2.0 import (`type: gip2`).
- Optional GIP source attributes in the export (`include_source_attributes`).
- Conda environment `netascore` (`environment.yml`, Python 3.13).

### Changed

- Settings and profile files require `version: 2.0`.
- Omitted `buffer` means no buffer (previously 500 m).
- `water` is a ratio from 0 to 100 (previously `true` or `false`).
- Refined OSM values for bicycle infrastructure, pedestrian infrastructure, road category, and pavement.
- `edge_id` is derived from the OSM way id and the segment position.
- Docker database image `postgis/postgis:18-3.6`.
- Dependencies: jinjasql2 replaces JinjaSql. Flask, igraph, and pandas are no longer required.

### Fixed

- Frequently failing Overpass API download requests
- OSM tag lookups for cycle-route scope, bicycle roads, unhewn cobblestone, and `sidewalk:right` / `sidewalk:both`.
- Noise re-import no longer duplicates values.
- Settings paths may contain a backslash.
- Missing input files report a readable error.
- Several minor bugs

### Removed

- Place-name filters `admin_level` and `zip_code`.
- Directional parking columns `parking_ft` and `parking_tf`.
