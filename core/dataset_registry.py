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
            reasons.append(("different area", "the existing data was imported for a different area that does not contain the current network extent"))
    return reasons


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
