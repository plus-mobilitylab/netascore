"""Helper class for metadata of a NetAScore run (stored in the db case schema and exported to the output GeoPackage).

Tables in the case schema (written by the processing steps, so that the information is kept if steps are skipped later):
- meta_run: key / value pairs (NetAScore version, settings, input file, steps of the last run incl. completion time, run duration, ...)
- meta_steps: one row per processing step (time, duration, NetAScore version, and settings of the run in which the step was executed last)
- meta_datasets: use of the input datasets in the attributes step (status, share of the network covered, ...)
- meta_profiles: mode profiles used in the index step
- meta_clip_area: area the network was clipped to (network step, OSM)

Layers in the output GeoPackage: meta_run, meta_steps, meta_datasets (incl. origin from the dataset registry), meta_profiles,
and meta_areas (AOI, clip area, network extent, and coverage of the input datasets).
"""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime

import toolbox.helper as h
from settings import DbSettings, GlobalSettings, NETASCORE_VERSION
from toolbox.dbhelper import PostgresConnection

META_RUN_TABLE = "meta_run"
META_STEPS_TABLE = "meta_steps"
META_DATASETS_TABLE = "meta_datasets"
META_PROFILES_TABLE = "meta_profiles"
META_CLIP_AREA_TABLE = "meta_clip_area"


def _connect(db_settings: DbSettings) -> PostgresConnection:
    db = PostgresConnection.from_settings_object(db_settings)
    db.execute(f"CREATE SCHEMA IF NOT EXISTS {db_settings.entities.network_schema};")
    return db


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def record_run_info(db_settings: DbSettings, values: dict) -> None:
    """Stores key / value pairs describing the run (existing keys are overwritten). Values are stored as text (dicts / lists as JSON)."""
    schema = db_settings.entities.network_schema
    db = _connect(db_settings)
    db.execute(f"CREATE TABLE IF NOT EXISTS {schema}.{META_RUN_TABLE} (key varchar PRIMARY KEY, value text);")
    for key, value in values.items():
        text = json.dumps(value) if isinstance(value, (dict, list)) else (None if value is None else str(value))
        db.execute(f"""INSERT INTO {schema}.{META_RUN_TABLE} (key, value) VALUES (%s, %s)
                       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;""", (key, text))
    db.commit()
    db.close()


# context of the current run (start time, settings, start time of the steps)
_run = {'started': None, 'settings': None, 'settings_file': None, 'step_started': {}}


def start_run(db_settings: DbSettings, settings: dict, settings_file: str, skipped_steps: list) -> None:
    """Records the start of a run. Information of the previous run that only refers to it (completed steps, export, duration)
    is removed from meta_run, so that meta_run describes the current run."""
    _run.update(started=datetime.now(), settings=sanitized_settings(settings), settings_file=settings_file, step_started={})
    schema = db_settings.entities.network_schema
    db = _connect(db_settings)
    db.execute(f"CREATE TABLE IF NOT EXISTS {schema}.{META_RUN_TABLE} (key varchar PRIMARY KEY, value text);")
    db.execute(f"""DELETE FROM {schema}.{META_RUN_TABLE}
                   WHERE key LIKE 'step\\_%%' OR key IN ('exported_at', 'output_file', 'run_duration_s');""")
    db.commit()
    db.close()
    record_run_info(db_settings, {
        'netascore_version': NETASCORE_VERSION,
        'started_at': _run['started'].isoformat(timespec='seconds'),
        'case_id': GlobalSettings.case_id,
        'settings_file': settings_file,
        'settings': _run['settings'],
        'skipped_steps': skipped_steps,
    })


def start_step(step: str) -> None:
    """Records the start time of a processing step."""
    _run['step_started'][step] = datetime.now()


def complete_step(db_settings: DbSettings, step: str) -> None:
    """Records the completion of a processing step: key 'step_<step>_completed_at' in meta_run (steps of the current run)
    and a row in meta_steps (incl. start time, duration, NetAScore version, and settings of the run)."""
    completed = datetime.now()
    started = _run['step_started'].get(step) or completed
    run_started = _run['started'] or started
    record_run_info(db_settings, {f"step_{step}_completed_at": completed.isoformat(timespec='seconds')})
    schema = db_settings.entities.network_schema
    db = _connect(db_settings)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS {schema}.{META_STEPS_TABLE} (
            step varchar PRIMARY KEY, run_started_at timestamp(0), step_started_at timestamp(0), step_completed_at timestamp(0),
            duration_s numeric, netascore_version varchar, settings_file varchar, settings text);
        INSERT INTO {schema}.{META_STEPS_TABLE} VALUES (%(step)s, %(run)s, %(started)s, %(completed)s, %(duration)s, %(version)s, %(file)s, %(settings)s)
        ON CONFLICT (step) DO UPDATE SET run_started_at = EXCLUDED.run_started_at, step_started_at = EXCLUDED.step_started_at,
            step_completed_at = EXCLUDED.step_completed_at, duration_s = EXCLUDED.duration_s, netascore_version = EXCLUDED.netascore_version,
            settings_file = EXCLUDED.settings_file, settings = EXCLUDED.settings;""",
        {'step': step, 'run': run_started.replace(microsecond=0), 'started': started.replace(microsecond=0),
         'completed': completed.replace(microsecond=0),
         'duration': round((completed - started).total_seconds(), 1), 'version': NETASCORE_VERSION,
         'file': _run['settings_file'], 'settings': json.dumps(_run['settings']) if _run['settings'] is not None else None})
    db.commit()
    db.close()


def record_run_duration(db_settings: DbSettings) -> None:
    """Records the duration of the current run so far (key 'run_duration_s')."""
    if _run['started'] is not None:
        record_run_info(db_settings, {'run_duration_s': round((datetime.now() - _run['started']).total_seconds())})


def sanitized_settings(settings: dict) -> dict:
    """Returns a copy of the settings without passwords."""
    if isinstance(settings, dict):
        return {k: ('***' if 'password' in str(k).lower() else sanitized_settings(v)) for k, v in settings.items()}
    if isinstance(settings, list):
        return [sanitized_settings(v) for v in settings]
    return settings


def osm_data_timestamp(path: str) -> str:
    """Returns the timestamp of the OSM data: 'osm_base' of an Overpass download, or the replication timestamp in the
    header of an OSM file (requires osmium). Returns None if not available."""
    if path.endswith('.xml') or path.endswith('.osm'):
        with open(path, encoding='utf-8', errors='ignore') as f:
            head = f.read(2000)
        match = re.search(r'osm_base="([^"]+)"', head)
        if match:
            return match.group(1)
    if shutil.which('osmium'):
        for option in ['osmosis_replication_timestamp', 'timestamp']:
            result = subprocess.run(['osmium', 'fileinfo', '-g', f'header.option.{option}', path], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    return None


def file_info(path: str) -> dict:
    """Name, size, and modification time of an input file."""
    if not os.path.exists(path):
        return {'file': os.path.basename(path)}
    stat = os.stat(path)
    return {'file': os.path.basename(path), 'size': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')}


def record_import_file(db_settings: DbSettings, import_settings: dict) -> None:
    """Records the input file of the import step (incl. modification time; for OSM also the timestamp of the data)."""
    import_type = str(import_settings.get('type')).lower()
    if import_settings.get('filename'):
        path = os.path.join(GlobalSettings.data_directory, str(import_settings['filename']))
    else:  # OSM download
        path = os.path.join(GlobalSettings.data_directory, f"{GlobalSettings.osm_download_prefix}_{GlobalSettings.case_id}.xml")
    values = {'import_type': import_type, 'import_file': file_info(path)}
    if import_type == 'osm' and os.path.exists(path):
        values['osm_data_timestamp'] = osm_data_timestamp(path)
    record_run_info(db_settings, values)


def record_datasets(db: PostgresConnection, schema: str, rows: list) -> None:
    """Stores how the input datasets are used in the attributes step (replaces previous information).
    Rows: dataset, indicator, status ('used', 'partial', 'not_used'), network_share_covered, transformed_crs, note."""
    db.execute(f"""
        DROP TABLE IF EXISTS {schema}.{META_DATASETS_TABLE};
        CREATE TABLE {schema}.{META_DATASETS_TABLE} (dataset varchar PRIMARY KEY, indicator varchar, status varchar,
                                                     network_share_covered numeric, transformed_crs boolean, note text);""")
    for row in rows:
        db.execute(f"""INSERT INTO {schema}.{META_DATASETS_TABLE} (dataset, indicator, status, network_share_covered, transformed_crs, note)
                       VALUES (%(dataset)s, %(indicator)s, %(status)s, %(network_share_covered)s, %(transformed_crs)s, %(note)s);""", row)
    db.commit()


def record_profiles(db_settings: DbSettings, profiles: list) -> None:
    """Stores the mode profiles used in the index step (replaces previous information)."""
    schema = db_settings.entities.network_schema
    db = _connect(db_settings)
    db.execute(f"""
        DROP TABLE IF EXISTS {schema}.{META_PROFILES_TABLE};
        CREATE TABLE {schema}.{META_PROFILES_TABLE} (profile_name varchar PRIMARY KEY, profile_file varchar, filter_access_car boolean,
            filter_access_bike boolean, filter_access_walk boolean, weights text, profile_content text);""")
    for p in profiles:
        db.execute(f"""INSERT INTO {schema}.{META_PROFILES_TABLE} VALUES (%s, %s, %s, %s, %s, %s, %s);""",
                   (p.profile_name, os.path.basename(p.filename), bool(p.access_car), bool(p.access_bike), bool(p.access_walk),
                    json.dumps({k: v for k, v in p.profile['weights'].items() if v is not None}), json.dumps(p.profile)))
    db.commit()
    db.close()


def create_meta_export_tables(db: PostgresConnection, schema: str, data_schema: str, target_srid: int) -> list:
    """Creates the metadata tables for the export (tables 'export_meta_*' in the case schema).
    Returns a list of (table, layer, geometry type) to export."""
    exports = []
    exists = lambda table, sch=schema: db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (f"{sch}.{table}",))[0]
    drop_meta_export_tables(db, schema)
    # run information
    if exists(META_RUN_TABLE):
        db.execute(f"CREATE TABLE {schema}.export_meta_run AS SELECT key, value FROM {schema}.{META_RUN_TABLE} ORDER BY key;")
        exports.append(('export_meta_run', 'meta_run', None))
    # processing steps
    if exists(META_STEPS_TABLE):
        db.execute(f"""CREATE TABLE {schema}.export_meta_steps AS
                       SELECT step, run_started_at::text, step_started_at::text, step_completed_at::text, duration_s,
                              netascore_version, settings_file, settings
                       FROM {schema}.{META_STEPS_TABLE} ORDER BY step_started_at;""")
        exports.append(('export_meta_steps', 'meta_steps', None))
    # input datasets: use in this case + origin from the dataset registry
    has_registry = exists('dataset_registry', data_schema)
    if exists(META_DATASETS_TABLE):
        origin_cols = ("r.source->>'file' AS source_file, to_timestamp((r.source->>'modified')::bigint)::timestamp(0)::text AS source_file_modified, (r.source->'layers')::text AS source_layers, "
                       "r.options::text AS import_options, r.srid AS stored_srid, r.import_extent IS NOT NULL AS clipped_on_import, "
                       "r.imported_at, r.case_id AS imported_by_case") if has_registry else "NULL::text AS source_file"
        origin_join = (f"LEFT JOIN {data_schema}.dataset_registry r ON r.dataset = d.dataset AND (r.status IS NULL OR r.status = 'complete')"
                       if has_registry else "")
        db.execute(f"""CREATE TABLE {schema}.export_meta_datasets AS
                       SELECT d.dataset, d.indicator, d.status, d.network_share_covered, d.transformed_crs, d.note, {origin_cols}
                       FROM {schema}.{META_DATASETS_TABLE} d {origin_join} ORDER BY d.dataset;""")
        exports.append(('export_meta_datasets', 'meta_datasets', None))
    # mode profiles
    if exists(META_PROFILES_TABLE):
        db.execute(f"CREATE TABLE {schema}.export_meta_profiles AS SELECT * FROM {schema}.{META_PROFILES_TABLE} ORDER BY profile_name;")
        exports.append(('export_meta_profiles', 'meta_profiles', None))
    # areas: AOI, clip area of the network, network extent, coverage of the input datasets used
    parts = []
    if exists('aoi', data_schema):
        parts.append(f"""SELECT 'aoi'::varchar AS area_type, NULL::varchar AS dataset, ST_Multi(ST_CollectionExtract(ST_Transform(geom, {target_srid}), 3)) AS geom
                         FROM {data_schema}.aoi WHERE name = '{GlobalSettings.case_id}'""")
    if exists(META_CLIP_AREA_TABLE):
        parts.append(f"""SELECT 'clip_area'::varchar, NULL::varchar, ST_Multi(ST_CollectionExtract(ST_Transform(geom, {target_srid}), 3))
                         FROM {schema}.{META_CLIP_AREA_TABLE}""")
    if exists('network_edge'):
        parts.append(f"""SELECT 'network_extent'::varchar, NULL::varchar, ST_Multi(ST_SetSRID(ST_Extent(geom)::geometry, {target_srid}))
                         FROM {schema}.network_edge""")
    if exists(META_DATASETS_TABLE) and has_registry:
        parts.append(f"""SELECT 'dataset_coverage'::varchar, r.dataset::varchar, ST_Multi(ST_CollectionExtract(ST_Transform(r.coverage, {target_srid}), 3))
                         FROM {data_schema}.dataset_registry r JOIN {schema}.{META_DATASETS_TABLE} d USING (dataset)
                         WHERE d.status IN ('used', 'partial') AND r.coverage IS NOT NULL""")
    if parts:
        db.execute(f"""CREATE TABLE {schema}.export_meta_areas AS
                       SELECT row_number() OVER ()::integer AS fid, area_type, dataset, geom::geometry(MultiPolygon, {target_srid}) AS geom
                       FROM ({' UNION ALL '.join(parts)}) t WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom);""")
        exports.append(('export_meta_areas', 'meta_areas', 'MULTIPOLYGON'))
    db.commit()
    return exports


def drop_meta_export_tables(db: PostgresConnection, schema: str) -> None:
    db.execute(f"DROP TABLE IF EXISTS {schema}.export_meta_run, {schema}.export_meta_steps, {schema}.export_meta_datasets, "
               f"{schema}.export_meta_profiles, {schema}.export_meta_areas;")
    db.commit()


def print_run_summary(db_settings: DbSettings) -> None:
    """Prints a summary of the run: output file, use of the input datasets, mode profiles."""
    schema = db_settings.entities.network_schema
    db = PostgresConnection.from_settings_object(db_settings)
    try:
        exists = lambda table: db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (f"{schema}.{table}",))[0]
        lines = [f"case: {GlobalSettings.case_id} (EPSG:{GlobalSettings.get_target_srid()})"]
        if exists(META_RUN_TABLE):
            output_file = db.query_one(f"SELECT value FROM {schema}.{META_RUN_TABLE} WHERE key = 'output_file';")
            if output_file:
                lines.append(f"output: {output_file[0]}")
        if exists(META_DATASETS_TABLE):
            lines.append("input datasets:")
            for dataset, status, share_covered, transformed_crs in db.query_all(
                    f"SELECT dataset, status, network_share_covered, transformed_crs FROM {schema}.{META_DATASETS_TABLE} ORDER BY dataset;"):
                details = f" ({float(share_covered) * 100:.1f} % of network covered)" if status == 'partial' else ""
                details += " - transformed to the target coordinate system" if transformed_crs else ""
                lines.append(f"  {dataset:10} {status}{details}")
        if exists(META_PROFILES_TABLE):
            names = [r[0] for r in db.query_all(f"SELECT profile_name FROM {schema}.{META_PROFILES_TABLE} ORDER BY profile_name;")]
            lines.append(f"profiles: {', '.join(names)}")
        db.commit()
        h.section("NetAScore run summary:\n  " + "\n  ".join(lines))
    finally:
        db.close()
