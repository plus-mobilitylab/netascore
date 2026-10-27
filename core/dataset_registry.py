"""Registry of datasets in the shared data schema (e.g. noise, buildings, greenness, DEM).
Purpose: store metadata per dataset - e.g. allow reuse of existing data if metadata/settings match
Metadata includes: source file and import options), CRS of stored data, spatial extend (subset of import or NULL 
for whole source file), area covered by the data (coverage)
Behavior based on 'on_existing' setting:
- reuse: reuse if the dataset matches the current settings, otherwise stop with an error
- reuse_or_overwrite: reuse if the dataset matches the current settings, otherwise import again
- overwrite: always import again
- abort: stop if the dataset already exists
"""
import json
import os
import sys

from osgeo import gdal, ogr, osr

import toolbox.helper as h
from settings import GlobalSettings
from toolbox.dbhelper import PostgresConnection

# GDAL/OGR errors raise exceptions (default from GDAL 4.0 on)
gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()

REGISTRY_TABLE = "dataset_registry"


def init_registry(db: PostgresConnection, schema: str) -> None:
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.{REGISTRY_TABLE} (
            dataset varchar PRIMARY KEY,
            source jsonb,                           -- source file(s) incl. size and modification time
            options jsonb,                          -- import settings that affect the content of the dataset
            srid integer,                           -- coordinate system of the stored data
            import_extent geometry(Polygon, 4326),  -- area requested on import (NULL: whole source file)
            coverage geometry(MultiPolygon, 4326),  -- area covered by the source data (within the import extent)
            imported_at timestamptz,
            case_id varchar,
            status varchar                          -- 'importing' (import started, not finished) or 'complete'
        );""")
    db.commit()


def file_signature(path: str, layers: list = None) -> dict:
    """Identifies a source file by its name, size, modification time (and imported layers, if relevant)."""
    stat = os.stat(path)
    return {'file': os.path.basename(path), 'size': stat.st_size, 'modified': int(stat.st_mtime),
            'layers': sorted(layers) if layers else None}


def _get_entry(db: PostgresConnection, schema: str, dataset: str) -> dict:
    row = db.query_one(f"SELECT source, options, import_extent IS NULL, status FROM {schema}.{REGISTRY_TABLE} WHERE dataset = %s;", (dataset,))
    if row is None:
        return None
    return {'source': row[0], 'options': row[1], 'full_import': row[2], 'interrupted': row[3] == 'importing'}


def get_registered(db: PostgresConnection, schema: str, dataset: str) -> dict:
    """Returns the registry entry of a completely imported dataset (srid, whether a coverage is known) - or None if the dataset
    is not registered (e.g. imported with an older version of NetAScore) or its import was not completed."""
    if not db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (f"{schema}.{REGISTRY_TABLE}",))[0]:
        return None
    row = db.query_one(f"""SELECT srid, coverage IS NOT NULL, case_id, imported_at FROM {schema}.{REGISTRY_TABLE}
                           WHERE dataset = %s AND status = 'complete';""", (dataset,))
    if row is None:
        return None
    return {'srid': row[0], 'has_coverage': row[1], 'case_id': row[2], 'imported_at': row[3]}


def _mismatches(db: PostgresConnection, schema: str, dataset: str, entry: dict, source: dict, options: dict, extent: tuple) -> list:
    """Returns the reasons why the registered dataset does not match the current settings (empty list: match)
    as tuples (short description, description incl. details)."""
    reasons = []
    # compare in the form stored in the registry (JSON: e.g. numeric keys of 'value_mapping' are converted to strings)
    source, options = json.loads(json.dumps(source)), json.loads(json.dumps(options))
    if entry['source'] != source:
        reasons.append(("different source data", f"different source data (existing: {entry['source']}, current: {source})"))
    if entry['options'] != options:
        reasons.append(("different import settings", f"different import settings (existing: {entry['options']}, current: {options})"))
    if extent and not entry['full_import']:
        covered = db.query_one(f"""SELECT ST_Covers(import_extent, ST_MakeEnvelope(%s, %s, %s, %s, 4326))
                                   FROM {schema}.{REGISTRY_TABLE} WHERE dataset = %s;""", (*extent, dataset))[0]
        if not covered:
            reasons.append(("different area", "the existing data was imported for a different area that does not cover the current one (network extent or area of interest)"))
    return reasons


def check_import_conflicts(db: PostgresConnection, schema: str, datasets: list, on_existing: str, source: dict, options: dict,
                           extent: tuple = None) -> None:
    """Checks whether prepare_import would stop for any of the datasets with the given 'on_existing' setting ('abort': dataset exists; 
    'reuse': existing dataset does not match) - raises an exception listing all of them. 
    Used before replacing data that other datasets depend on (e.g. the OSM tables)."""
    if on_existing not in ('reuse', 'abort'):
        return
    init_registry(db, schema)
    conflicts = []
    for dataset in datasets:
        entry = _get_entry(db, schema, dataset)
        if not db.exists(dataset, schema) or (entry is not None and entry['interrupted']):
            continue  # imported anyway
        if on_existing == 'abort':
            conflicts.append(f"'{dataset}' already exists")
        elif entry is not None:
            reasons = _mismatches(db, schema, dataset, entry, source, options, extent)
            if reasons:
                conflicts.append(f"'{dataset}' does not match the current settings ({', '.join(s for s, _ in reasons)})")
    if conflicts:
        raise Exception(f"Existing dataset(s) {'; '.join(conflicts)} - with 'on_existing: {on_existing}' they would not be replaced. "
                        "Nothing was changed. Set 'on_existing: reuse_or_overwrite' (or 'overwrite') in the import settings to import them again.")


def prepare_import(db: PostgresConnection, schema: str, dataset: str, tables: list, on_existing: str,
                   source: dict, options: dict, extent: tuple = None) -> bool:
    """Decides whether the dataset needs to be imported (True) or the existing data is reused (False).
    Existing tables are dropped if the dataset is imported again."""
    init_registry(db, schema)
    entry = _get_entry(db, schema, dataset)
    if not any(db.exists(table, schema) for table in tables):
        _start_import(db, schema, dataset, tables, source, options)
        return True
    if entry is not None and entry['interrupted']:
        # a previous import did not finish (e.g. error or cancelled run): existing data is incomplete
        h.majorInfo(f"WARNING: the previous import of dataset '{dataset}' was interrupted - importing it again.")
        _start_import(db, schema, dataset, tables, source, options)
        return True
    if on_existing == 'abort':
        raise Exception(f"Dataset '{dataset}' already exists. Please resolve the conflict manually or set 'on_existing' "
                        "to 'reuse', 'reuse_or_overwrite', or 'overwrite'.")
    reasons = []
    if on_existing != 'overwrite':
        if entry is None:
            if on_existing == 'reuse':
                h.majorInfo(f"WARNING: reusing existing dataset '{dataset}' of unknown origin (imported with an older version of NetAScore) - "
                            "it cannot be verified that it matches the current settings.")
                return False
            reasons = [("unknown origin", "unknown origin (imported with an older version of NetAScore)")]
        else:
            reasons = _mismatches(db, schema, dataset, entry, source, options, extent)
            if not reasons:
                h.info(f"reusing existing dataset '{dataset}' (matches the current settings)")
                return False
            if on_existing == 'reuse':
                h.majorInfo(f"error: existing dataset '{dataset}' does not match the current settings:\n  - " + "\n  - ".join(d for _, d in reasons) +
                            "\nSet 'on_existing: reuse_or_overwrite' (or 'overwrite') to import the new dataset - this replaces the previous one")
                sys.exit(1)
    h.majorInfo(f"importing dataset '{dataset}', overwriting previous one.")
    if reasons:
        # log level 1: short reasons; from log level 2 on: reasons incl. details (existing / current source and settings)
        if h.get_current_log_level() >= h.LOG_LEVEL_2_INFO:
            h.info(f"reasons for re-importing dataset '{dataset}':\n  - " + "\n  - ".join(d for _, d in reasons))
        else:
            h.majorInfo(f"reasons for re-importing dataset '{dataset}': {', '.join(s for s, _ in reasons)}")
    _start_import(db, schema, dataset, tables, source, options)
    return True


def _start_import(db: PostgresConnection, schema: str, dataset: str, tables: list, source: dict, options: dict) -> None:
    """Drops existing tables of the dataset and records the start of the import (status 'importing' until register() is called)."""
    for table in tables:
        if db.exists(table, schema):
            db.drop_table(table, cascade=True, schema=schema)
    db.execute(f"""
        INSERT INTO {schema}.{REGISTRY_TABLE} (dataset, source, options, imported_at, case_id, status)
        VALUES (%(dataset)s, %(source)s, %(options)s, now(), %(case_id)s, 'importing')
        ON CONFLICT (dataset) DO UPDATE SET source = EXCLUDED.source, options = EXCLUDED.options, srid = NULL, import_extent = NULL,
            coverage = NULL, imported_at = EXCLUDED.imported_at, case_id = EXCLUDED.case_id, status = EXCLUDED.status;
        """, {'dataset': dataset, 'source': json.dumps(source), 'options': json.dumps(options), 'case_id': GlobalSettings.case_id})
    db.commit()


def remove(db: PostgresConnection, schema: str, dataset: str) -> None:
    """Removes the registry entry of a dataset (e.g. if nothing was imported)."""
    db.execute(f"DELETE FROM {schema}.{REGISTRY_TABLE} WHERE dataset = %s;", (dataset,))
    db.commit()


def register(db: PostgresConnection, schema: str, dataset: str, source: dict, options: dict, srid: int,
             extent: tuple = None, coverage_wkt: str = None) -> None:
    """Records a dataset after a successful import (status 'complete'). The coverage (WKT, WGS84) is limited to the import extent."""
    init_registry(db, schema)
    db.execute(f"""
        INSERT INTO {schema}.{REGISTRY_TABLE} (dataset, source, options, srid, import_extent, coverage, imported_at, case_id, status)
        WITH e AS (SELECT CASE WHEN %(has_extent)s THEN ST_MakeEnvelope(%(x1)s, %(y1)s, %(x2)s, %(y2)s, 4326) END AS geom),
             c AS (SELECT ST_GeomFromText(%(coverage)s, 4326) AS geom)
        SELECT %(dataset)s, %(source)s, %(options)s, %(srid)s, e.geom,
               -- only areas count as coverage (lines/points from touching boundaries are removed; empty: no coverage);
               -- edges are densified (vertex every 0.01 deg) to keep their shape when transformed to other coordinate systems
               ST_Multi(ST_CollectionExtract(ST_Segmentize(CASE WHEN c.geom IS NULL THEN e.geom WHEN e.geom IS NULL THEN c.geom ELSE ST_Intersection(c.geom, e.geom) END, 0.01), 3)),
               now(), %(case_id)s, 'complete'
        FROM e, c
        ON CONFLICT (dataset) DO UPDATE SET source = EXCLUDED.source, options = EXCLUDED.options, srid = EXCLUDED.srid,
            import_extent = EXCLUDED.import_extent, coverage = EXCLUDED.coverage, imported_at = EXCLUDED.imported_at, case_id = EXCLUDED.case_id,
            status = EXCLUDED.status;
        """, {'has_extent': extent is not None, 'x1': extent[0] if extent else None, 'y1': extent[1] if extent else None,
              'x2': extent[2] if extent else None, 'y2': extent[3] if extent else None, 'coverage': coverage_wkt,
              'dataset': dataset, 'source': json.dumps(source), 'options': json.dumps(options), 'srid': srid,
              'case_id': GlobalSettings.case_id})
    db.commit()


# --- OSM import (tables osm_point, osm_line, osm_polygon, osm_bicycle_route) ---
# The OSM tables in the shared data schema are replaced by each OSM import (also by the optional OSM import of other
# cases). The network step now checks that they were imported for the current case. They are not part of
# the dataset registry, as they are not used as input datasets of the attributes step.

OSM_IMPORT_TABLE = "osm_import"


def start_osm_import(db: PostgresConnection, schema: str, record_table: str = OSM_IMPORT_TABLE) -> None:
    """Removes the record of the previous OSM import (the OSM tables are replaced - incomplete if the import fails).
    Also used for GIP imports (record_table: see GIP_IMPORT_TABLES)."""
    db.execute(f"DROP TABLE IF EXISTS {schema}.{record_table};")
    db.commit()


def record_osm_import(db: PostgresConnection, schema: str, source: dict, options: dict, extent: tuple = None,
                      record_table: str = OSM_IMPORT_TABLE) -> None:
    """Records a completed OSM import: case, source file, settings affecting the imported area, and extracted area
    (min lon, min lat, max lon, max lat; None: whole file). Also used for GIP imports (record_table: see GIP_IMPORT_TABLES)."""
    db.execute(f"""
        DROP TABLE IF EXISTS {schema}.{record_table};
        CREATE TABLE {schema}.{record_table} (case_id varchar, source jsonb, options jsonb,
                                             import_extent geometry(Polygon, 4326), imported_at timestamptz);
        INSERT INTO {schema}.{record_table}
        SELECT %(case_id)s, %(source)s, %(options)s,
               CASE WHEN %(has_extent)s THEN ST_MakeEnvelope(%(x1)s, %(y1)s, %(x2)s, %(y2)s, 4326) END, now();
        """, {'case_id': GlobalSettings.case_id, 'source': json.dumps(source), 'options': json.dumps(options),
              'has_extent': extent is not None, 'x1': extent[0] if extent else None, 'y1': extent[1] if extent else None,
              'x2': extent[2] if extent else None, 'y2': extent[3] if extent else None})
    db.commit()


def check_osm_import(db: PostgresConnection, schema: str) -> None:
    """Ensures that the OSM tables in the data schema were imported for the current case"""
    row = None
    if db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (f"{schema}.{OSM_IMPORT_TABLE}",))[0]:
        row = db.query_one(f"SELECT case_id, source->>'file', imported_at FROM {schema}.{OSM_IMPORT_TABLE};")
    if row is None:
        raise Exception(f"No completed OSM import found in schema '{schema}' (import not run, failed, or ran with an older "
                        "version of NetAScore). Please run the import step (again).")
    case_id, source_file, imported_at = row
    if case_id != GlobalSettings.case_id:
        raise Exception(f"The OSM data in schema '{schema}' was imported for case '{case_id}' ({source_file}, "
                        f"{imported_at:%Y-%m-%d %H:%M}) - not for the current case '{GlobalSettings.case_id}'. "
                        "Please run the import step (again) for the current case.")


def check_osm_import_extent(db: PostgresConnection, schema: str, clip_area_wkt: str = None) -> None:
    """Ensures that the OSM data (imported for the current case, see check_osm_import) covers the area the network is
    clipped to (WKT, WGS84; None: network not clipped) - e.g. not if 'buffer' or 'clip' were changed and the import step
    was skipped."""
    import_extent, options = db.query_one(f"SELECT ST_AsText(import_extent), options FROM {schema}.{OSM_IMPORT_TABLE};")
    if import_extent is None:  # whole OSM file imported
        return
    if clip_area_wkt is None:
        raise Exception(f"The OSM data was only imported for the area of interest (import settings: {options}), but the network "
                        "is not clipped to it now (no AOI or 'clip: none'). Please run the import step again.")
    covered = db.query_one("SELECT ST_Covers(ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326));", (import_extent, clip_area_wkt))[0]
    if not covered:
        raise Exception(f"The area the network is clipped to (current settings 'buffer' / 'clip') extends beyond the area the OSM "
                        f"data was imported for (import settings: {options}). Please run the import step again.")



# --- GIP import (tables gip_* / gip2_*) ---
# Like the OSM tables, the GIP tables in the shared data schema are not part of the dataset registry. They contain the
# whole GIP dataset (covering Austria), so they can be used by all GIP cases - the import record identifies the source file.

GIP_IMPORT_TABLES = {'gip': "gip_import", 'gip2': "gip2_import"}


def _get_import_source(db: PostgresConnection, schema: str, record_table: str) -> tuple:
    """Returns source and case of the recorded (completed) import - or None if there is no record."""
    if not db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (f"{schema}.{record_table}",))[0]:
        return None
    return db.query_one(f"SELECT source, case_id, imported_at FROM {schema}.{record_table};")


def start_gip_import(db: PostgresConnection, schema: str, import_type: str) -> None:
    """Removes the record of the previous GIP import (the GIP tables are replaced - incomplete if the import fails)."""
    start_osm_import(db, schema, GIP_IMPORT_TABLES[import_type])


def record_gip_import(db: PostgresConnection, schema: str, import_type: str, source: dict) -> None:
    """Records a completed GIP import (case, source file)."""
    record_osm_import(db, schema, source, {}, record_table=GIP_IMPORT_TABLES[import_type])


def gip_import_needed(db: PostgresConnection, schema: str, import_type: str, tables: list, on_existing: str, source: dict) -> bool:
    """Decides whether the GIP tables need to be imported (True) or the existing ones are reused (False) - based on the
    import record and the 'on_existing' setting. Tables without import record (import interrupted or imported with an
    older version of NetAScore) are imported again."""
    if not all(db.exists(table, schema) for table in tables):
        return True
    if on_existing == 'abort':
        raise Exception(f"The {import_type.upper()} tables already exist in schema '{schema}'. Please resolve the conflict manually "
                        "or set 'on_existing' to 'reuse', 'reuse_or_overwrite', or 'overwrite'.")
    if on_existing == 'overwrite':
        h.majorInfo(f"importing {import_type.upper()} data, overwriting the existing tables ('on_existing: overwrite').")
        return True
    record = _get_import_source(db, schema, GIP_IMPORT_TABLES[import_type])
    if record is None:
        h.majorInfo(f"importing {import_type.upper()} data again: the existing tables have no import record (previous import "
                    "interrupted or imported with an older version of NetAScore).")
        return True
    existing, case_id, imported_at = record
    if existing == json.loads(json.dumps(source)):
        h.info(f"reusing the existing {import_type.upper()} tables (imported from the same file '{source['file']}' for case "
               f"'{case_id}', {imported_at:%Y-%m-%d %H:%M})")
        return False
    if on_existing == 'reuse':
        raise Exception(f"The existing {import_type.upper()} tables were imported from a different or changed source file (existing: "
                        f"{existing}, current: {source}). Set 'on_existing: reuse_or_overwrite' (or 'overwrite') in the import settings to "
                        "import the current file - this replaces the existing tables (used by all GIP cases).")
    changed = "the file was changed since" if existing.get('file') == source['file'] else f"imported from '{existing.get('file')}'"
    h.majorInfo(f"importing {import_type.upper()} data, overwriting the existing tables ({changed}).")
    return True


def check_gip_import(db: PostgresConnection, schema: str, import_type: str, filename: str) -> None:
    """Ensures that the GIP tables in the data schema were imported from the file given in the import settings (they may
    have been replaced by another case since)."""
    record = _get_import_source(db, schema, GIP_IMPORT_TABLES[import_type])
    if record is None:
        raise Exception(f"No completed {import_type.upper()} import found in schema '{schema}' (import not run, failed, or ran "
                        "with an older version of NetAScore). Please run the import step (again).")
    if not filename:
        return
    existing, case_id, imported_at = record
    path = os.path.join(GlobalSettings.data_directory, filename)
    # compare the whole file signature if the file is available, otherwise only the file name
    current = json.loads(json.dumps(file_signature(path))) if os.path.isfile(path) else {'file': os.path.basename(path)}
    if any(existing.get(key) != value for key, value in current.items()):
        raise Exception(f"The {import_type.upper()} data in schema '{schema}' was imported from a different file ({existing}, "
                        f"for case '{case_id}', {imported_at:%Y-%m-%d %H:%M}) than given in the import settings ({current}). "
                        "Please run the import step (again).")


# --- coverage of source data (WKT polygon in WGS84) ---

def _wgs84() -> osr.SpatialReference:
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)  # lon/lat
    return srs


def _bbox_to_wgs84(bbox: tuple, srs: osr.SpatialReference) -> ogr.Geometry:
    """Transforms a bounding box (min x, max x, min y, max y as returned by OGR) to a polygon in WGS84."""
    min_x, max_x, min_y, max_y = bbox
    geom = ogr.CreateGeometryFromWkt(f"POLYGON(({min_x} {min_y}, {max_x} {min_y}, {max_x} {max_y}, {min_x} {max_y}, {min_x} {min_y}))")
    geom.Segmentize(max(max_x - min_x, max_y - min_y) / 20)  # densify edges for an accurate transformation
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    geom.Transform(osr.CoordinateTransformation(srs, _wgs84()))
    return geom


def vector_coverage(path: str, layers: list = None) -> str:
    """Coverage of vector data: bounding box(es) of the given layers (all layers with geometry if None)."""
    data_source = ogr.Open(path)
    union = None
    for layer in data_source:
        if layer.GetGeomType() == ogr.wkbNone or (layers and layer.GetName() not in layers) or layer.GetSpatialRef() is None:
            continue
        geom = _bbox_to_wgs84(layer.GetExtent(), layer.GetSpatialRef().Clone())
        union = geom if union is None else union.Union(geom)
    return union.ExportToWkt() if union is not None else None


def raster_coverage(path: str, srid: int) -> str:
    """Coverage of raster data: extent of the raster (in the given coordinate system)."""
    raster = gdal.Open(path)
    gt = raster.GetGeoTransform()
    xs = sorted([gt[0], gt[0] + gt[1] * raster.RasterXSize])
    ys = sorted([gt[3], gt[3] + gt[5] * raster.RasterYSize])
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(srid)
    return _bbox_to_wgs84((xs[0], xs[1], ys[0], ys[1]), srs).ExportToWkt()


def coverage_from_file(path: str) -> str:
    """Coverage given by the user (setting 'coverage'): union of all polygons in the given file."""
    if not os.path.exists(path):
        raise Exception(f"The provided coverage file could not be found. Please check file location and name for '{path}'")
    data_source = ogr.Open(path)
    union = None
    for layer in data_source:
        if layer.GetGeomType() == ogr.wkbNone:
            continue
        srs = layer.GetSpatialRef()
        if srs is None:
            raise Exception(f"The coverage file '{path}' has no coordinate system.")
        srs = srs.Clone()
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        transform = osr.CoordinateTransformation(srs, _wgs84())
        for feature in layer:
            geom = feature.GetGeometryRef()
            if geom is None or geom.IsEmpty():
                continue
            geom = geom.Clone()
            geom.Transform(transform)
            union = geom if union is None else union.Union(geom)
    if union is None:
        raise Exception(f"The coverage file '{path}' does not contain any polygons.")
    return union.ExportToWkt()
