"""Helper class for metadata of a NetAScore run (stored in the db case schema and exported to the output GeoPackage).

Tables in the case schema (written by the processing steps, so that the information is kept if steps are skipped later):
- meta_run: key / value pairs (NetAScore version, settings, input file, steps of the last run incl. completion time, run duration, ...)
- meta_steps: one row per processing step (time, duration, NetAScore version, and settings of the run in which the step was executed last)
- meta_datasets: use of the input datasets in the attributes step (status, share of the network covered, ...) and their origin
  (dataset registry entry at that time - shared datasets may be replaced later, e.g. by another case)
- meta_profiles: mode profiles used in the index step
- meta_clip_area: area the network was clipped to (network step, OSM)
- meta_aoi: AOI the network is based on (network step, OSM - the shared AOI table may change with later imports)

Layers in the output GeoPackage: meta_run, meta_steps, meta_datasets (incl. origin of the data used), meta_profiles,
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
META_AOI_TABLE = "meta_aoi"


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


def record_datasets(db: PostgresConnection, schema: str, rows: list, data_schema: str) -> None:
    """Stores how the input datasets are used in the attributes step (replaces previous information).
    Rows: dataset, indicator, status ('used', 'partial', 'not_used'), network_share_covered, transformed_crs, note.
    The origin of the datasets (dataset registry entry) is stored as well: shared datasets may be replaced later (e.g. by
    another case), while the attributes of this case are still based on the data used here."""
    db.execute(f"""
        DROP TABLE IF EXISTS {schema}.{META_DATASETS_TABLE};
        CREATE TABLE {schema}.{META_DATASETS_TABLE} (dataset varchar PRIMARY KEY, indicator varchar, status varchar,
                                                     network_share_covered numeric, transformed_crs boolean, note text,
                                                     source jsonb, options jsonb, stored_srid integer, clipped_on_import boolean,
                                                     coverage geometry(MultiPolygon, 4326), imported_at timestamptz, imported_by_case varchar);""")
    for row in rows:
        db.execute(f"""INSERT INTO {schema}.{META_DATASETS_TABLE} (dataset, indicator, status, network_share_covered, transformed_crs, note)
                       VALUES (%(dataset)s, %(indicator)s, %(status)s, %(network_share_covered)s, %(transformed_crs)s, %(note)s);""", row)
    if db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (f"{data_schema}.dataset_registry",))[0]:
        db.execute(f"""UPDATE {schema}.{META_DATASETS_TABLE} d
                       SET source = r.source, options = r.options, stored_srid = r.srid, clipped_on_import = r.import_extent IS NOT NULL,
                           coverage = r.coverage, imported_at = r.imported_at, imported_by_case = r.case_id
                       FROM {data_schema}.dataset_registry r
                       WHERE r.dataset = d.dataset AND r.status = 'complete';""")
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
    # input datasets: use in this case + origin of the data used (as recorded in the attributes step)
    if exists(META_DATASETS_TABLE):
        db.execute(f"""CREATE TABLE {schema}.export_meta_datasets AS
                       SELECT dataset, indicator, status, network_share_covered, transformed_crs, note,
                              source->>'file' AS source_file, to_timestamp((source->>'modified')::bigint)::timestamp(0)::text AS source_file_modified,
                              (source->'layers')::text AS source_layers, options::text AS import_options, stored_srid, clipped_on_import,
                              imported_at, imported_by_case
                       FROM {schema}.{META_DATASETS_TABLE} ORDER BY dataset;""")
        exports.append(('export_meta_datasets', 'meta_datasets', None))
    # mode profiles
    if exists(META_PROFILES_TABLE):
        db.execute(f"CREATE TABLE {schema}.export_meta_profiles AS SELECT * FROM {schema}.{META_PROFILES_TABLE} ORDER BY profile_name;")
        exports.append(('export_meta_profiles', 'meta_profiles', None))
    # areas: AOI, clip area of the network, network extent, coverage of the input datasets used
    parts = []
    # AOI the network is based on (stored by the network step - not the current entry of the shared AOI table)
    if exists(META_AOI_TABLE):
        parts.append(f"""SELECT 'aoi'::varchar AS area_type, NULL::varchar AS dataset, ST_Multi(ST_CollectionExtract(ST_Transform(geom, {target_srid}), 3)) AS geom
                         FROM {schema}.{META_AOI_TABLE}""")
    if exists(META_CLIP_AREA_TABLE):
        parts.append(f"""SELECT 'clip_area'::varchar, NULL::varchar, ST_Multi(ST_CollectionExtract(ST_Transform(geom, {target_srid}), 3))
                         FROM {schema}.{META_CLIP_AREA_TABLE}""")
    if exists('network_edge'):
        parts.append(f"""SELECT 'network_extent'::varchar, NULL::varchar, ST_Multi(ST_SetSRID(ST_Extent(geom)::geometry, {target_srid}))
                         FROM {schema}.network_edge""")
    if exists(META_DATASETS_TABLE):
        parts.append(f"""SELECT 'dataset_coverage'::varchar, dataset::varchar, ST_Multi(ST_CollectionExtract(ST_Transform(coverage, {target_srid}), 3))
                         FROM {schema}.{META_DATASETS_TABLE} WHERE status IN ('used', 'partial') AND coverage IS NOT NULL""")
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


def _step_completed(db: PostgresConnection, schema: str, step: str) -> tuple:
    """Returns the last execution of a processing step (time / current run)."""
    exists = lambda table: db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (f"{schema}.{table}",))[0]
    in_run = exists(META_RUN_TABLE) and db.query_one(
        f"SELECT count(*) > 0 FROM {schema}.{META_RUN_TABLE} WHERE key = %s;", (f"step_{step}_completed_at",))[0]
    last = db.query_one(f"SELECT step_completed_at FROM {schema}.{META_STEPS_TABLE} WHERE step = %s;", (step,)) if exists(META_STEPS_TABLE) else None
    return in_run, (last[0] if last else None)


def dataset_changes(db: PostgresConnection, schema: str, data_schema: str) -> tuple:
    """Compares the input datasets used in the last attributes step of the case with the datasets currently stored (registry).
    Returns (warnings, notes):
    - warnings: datasets imported for this case after its last attributes step - the output does not reflect them yet
    - notes: datasets used by this case that were replaced since (e.g. by another case) - the output is still based on the
      data used then, re-running the attributes step imports it again"""
    warnings, notes = [], []
    exists = lambda table, sch=schema: db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (f"{sch}.{table}",))[0]
    if not exists(META_DATASETS_TABLE) or not exists('dataset_registry', data_schema):
        return warnings, notes
    rows = db.query_all(f"""
        SELECT coalesce(d.dataset, r.dataset), d.status, d.imported_at, r.imported_at, r.case_id, r.source->>'file'
        FROM {schema}.{META_DATASETS_TABLE} d
            FULL JOIN (SELECT * FROM {data_schema}.dataset_registry WHERE status = 'complete') r USING (dataset)
        WHERE r.imported_at IS DISTINCT FROM d.imported_at
            -- re-imported from the same source with the same settings and coverage: same data
            AND NOT (r.source IS NOT DISTINCT FROM d.source AND r.options IS NOT DISTINCT FROM d.options
                     AND r.coverage IS NOT DISTINCT FROM d.coverage AND d.source IS NOT NULL)
        ORDER BY 1;""")
    imported, replaced = {}, {}  # grouped by source file / replacement
    for dataset, status, used_imported_at, imported_at, case_id, source_file in rows:
        if imported_at is not None and case_id == GlobalSettings.case_id:
            # imported for this case after its attributes step (new dataset or replaced one)
            imported.setdefault(source_file, []).append(dataset)
        elif status in ('used', 'partial'):
            now = f"now: {source_file}, imported for case '{case_id}'" if imported_at is not None else "no longer available"
            replaced.setdefault(now, []).append(dataset)
    names = lambda datasets: ("dataset " if len(datasets) == 1 else "datasets ") + ", ".join(f"'{d}'" for d in datasets)
    for source_file, datasets in imported.items():
        warnings.append(f"{names(datasets)} ({source_file}) imported after the last attributes step - the output does not reflect "
                        f"{'it' if len(datasets) == 1 else 'them'} yet. Run the attributes step (and the following steps) to use the current data.")
    for now, datasets in replaced.items():
        notes.append(f"{names(datasets)} used by this case replaced since its attributes step ({now}) - the output is based on the data "
                     f"used then. Re-running the attributes step imports {'it' if len(datasets) == 1 else 'them'} again.")
    return warnings, notes


def print_run_summary(db_settings: DbSettings) -> None:
    """Prints a summary of the run: output file, use of the input datasets, mode profiles - and warnings in case the input
    datasets changed after the last attributes step of the case."""
    schema = db_settings.entities.network_schema
    db = PostgresConnection.from_settings_object(db_settings)
    try:
        exists = lambda table: db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (f"{schema}.{table}",))[0]

        def as_of(step: str) -> str:
            # information of a step that was skipped in this run: label with the time of its last execution
            in_run, last = _step_completed(db, schema, step)
            return "" if in_run or last is None else f" (as of {step} step {last:%Y-%m-%d %H:%M})"

        lines = [f"case: {GlobalSettings.case_id} (EPSG:{GlobalSettings.get_target_srid()})"]
        if exists(META_RUN_TABLE):
            output_file = db.query_one(f"SELECT value FROM {schema}.{META_RUN_TABLE} WHERE key = 'output_file';")
            if output_file:
                lines.append(f"output: {output_file[0]}")
        if exists(META_DATASETS_TABLE):
            lines.append(f"input datasets{as_of('attributes')}:")
            for dataset, status, share_covered, transformed_crs, source_file, imported_at, imported_by_case in db.query_all(
                    f"""SELECT dataset, status, network_share_covered, transformed_crs, source->>'file', imported_at, imported_by_case
                        FROM {schema}.{META_DATASETS_TABLE} ORDER BY dataset;"""):
                # origin: source file, import time (and case, if imported for another case)
                source = ""
                if source_file:
                    # imported in the current run: 'imported now'
                    in_run = imported_at is not None and _run['started'] is not None \
                        and imported_at.astimezone().replace(tzinfo=None) >= _run['started']
                    imported = "imported now" if in_run else (f"imported {imported_at:%Y-%m-%d %H:%M}" if imported_at else "")
                    if imported_by_case and imported_by_case != GlobalSettings.case_id:
                        imported += f" for case '{imported_by_case}'"
                    source = f"  {source_file}" + (f" ({imported.strip()})" if imported else "")
                details = f" ({float(share_covered) * 100:.1f} % of network covered)" if status == 'partial' else ""
                details += " - transformed to the target coordinate system" if transformed_crs else ""
                lines.append(f"  {dataset:10} {status:8}{source}{details}".rstrip())
        if exists(META_PROFILES_TABLE):
            names = [r[0] for r in db.query_all(f"SELECT profile_name FROM {schema}.{META_PROFILES_TABLE} ORDER BY profile_name;")]
            lines.append(f"profiles{as_of('index')}: {', '.join(names)}")
        warnings, notes = dataset_changes(db, schema, db_settings.entities.data_schema)
        db.commit()
        h.section("NetAScore run summary:\n  " + "\n  ".join(lines))
        for warning in warnings:
            h.majorInfo(f"WARNING: {warning}")
        for note in notes:
            h.info(f"NOTE: {note}")
    finally:
        db.close()