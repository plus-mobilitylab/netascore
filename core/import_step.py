import math
import os
import re
import shutil
import subprocess
import sys
from urllib.error import HTTPError
import urllib.request
import zipfile
from osgeo import ogr
from typing import List

import toolbox.helper as h
from core import dataset_registry as registry
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings, InputType
from toolbox.dbhelper import PostgresConnection

# GDAL/OGR errors raise exceptions (default from GDAL 4.0 on)
ogr.UseExceptions()


def _remove_file(path: str) -> None:
    if os.path.isfile(path):
        os.remove(path)


def _overpass_response_error(path: str) -> str:
    """Checks a downloaded Overpass API response. Returns an error description if the response is no OSM XML, reports an
    error during query execution (remark, e.g. 'runtime error: Query timed out' - HTTP status 200), or is incomplete
    (no closing '</osm>', e.g. connection dropped), otherwise None.
    Only the start and the end of the file are read: the remark follows the header if the query fails before any output,
    and precedes '</osm>' if it fails during the output."""
    with open(path, 'rb') as f:
        head = f.read(5000).decode('utf-8', errors='replace')
        f.seek(max(0, os.path.getsize(path) - 5000))
        tail = f.read().decode('utf-8', errors='replace')
    if '<osm' not in head:
        excerpt = re.sub(r"\s+", " ", head)[:200]
        return f"response is no OSM data: {excerpt}"
    for part in (head, tail):
        for remark in re.findall(r"<remark>(.*?)</remark>", part, flags=re.S):
            if 'error' in remark.lower():
                return f"Overpass API reported an error (data incomplete): {remark.strip()}"
    if not tail.rstrip().endswith('</osm>'):
        return "incomplete response (OSM data does not end with '</osm>')"
    return None


def create_csv(file_txt: str) -> None:
    """Takes in a path to an ogd gip txt file and converts it to a csv file."""
    with open(file_txt, 'r', encoding='iso-8859-1') as f:
        for line in f:
            if line.startswith('tbl;'):
                file_csv = open(os.path.splitext(file_txt)[0] + '.csv', 'w', encoding='utf-8')
            elif line.startswith('atr;'):
                file_csv.write(line[4:])
            elif line.startswith('rec;'):
                file_csv.write(line[4:].replace('""', '').replace('" "', ''))

    file_csv.close()


def create_sql(file_txt: str) -> None:
    """Takes in a path to an ogd gip txt file and creates a sql file from it."""
    with open(file_txt, 'r', encoding='iso-8859-1') as f:
        for line in f:
            if line.startswith('tbl;'):
                file_sql = open(os.path.splitext(file_txt)[0] + '.sql', 'w', encoding='utf-8')
                tbl = line[4:].strip().lower()
            elif line.startswith('atr;'):
                atr = line[4:].strip().lower().split(';')
            elif line.startswith('frm;'):
                frm = line[4:].strip().lower().split(';')
            elif line.startswith('rec;'):
                break

    for i, atr_ in enumerate(atr):
        if atr_ == 'offset':
            atr[i] = 'offset_'

    for i, frm_ in enumerate(frm):
        if frm_ == 'string':
            frm[i] = 'varchar'
        if m := re.search(r"^(string)[(]([0-9]*)[)]", frm_):
            length = m.group(2)
            frm[i] = f"varchar({length})"
        elif m := re.search(r"^(decimal)[(]([0-9]*)[,]([0-9]*)[)]", frm_):
            precision = m.group(2)
            scale = m.group(3)
            frm[i] = f"numeric({precision},{scale})"
        elif m := re.search(r"^(decimal)[(]([0-9]*)[)]", frm_):
            precision = m.group(2)
            if int(precision) <= 4:
                frm[i] = "smallint"
            elif int(precision) <= 10:
                frm[i] = "integer"
            elif int(precision) <= 18:
                frm[i] = "bigint"
            else:
                frm[i] = f"numeric({precision})"

    columns = [f"{atr_} {frm_}" for atr_, frm_ in zip(atr, frm)]
    sql = f"CREATE TABLE gip_{tbl} ({', '.join(columns)});"

    file_sql.write(sql)
    file_sql.close()


def import_csv(connection_string: str, path: str, schema: str, table: str) -> None:
    """Takes in a path to a csv file and imports it to a database table."""
    h.log(f"Importing CSV '{path}' into database: '{schema}.{table}'")
    # INFO: for psql in Windows, connection_string MUST be the LAST parameter - otherwise, further arguments are ignored
    subprocess.run(['psql', '-c', f"\\copy {schema}.{table} from '{path}' WITH CSV DELIMITER ';' NULL '' HEADER ENCODING 'utf-8'", connection_string],
        check=True)


def import_geopackage(connection_string: str, path: str, schema: str, table: str, fid: str = None, target_srid: int = None, layers: List[str] = None,  attributes: List[str] = None, geometry_types: List[str] = None, extent: tuple = None) -> None:  # TODO: @CW: extend error handling
    """Takes in a path to a geopackage file and imports it to a database table."""
    if not os.path.exists(path):
        raise Exception(f"The provided input file could not be found. Please check file location and name for '{path}'")
    data_source = ogr.Open(path)

    attributes = [] if attributes is None else attributes
    attributes = ','.join(attribute for attribute in attributes)

    geometry_types = [] if geometry_types is None else geometry_types
    geometry_types = ', '.join(f"'{geometry_type}'" for geometry_type in geometry_types)

    layers = [layer.GetName() for layer in data_source] if layers is None else layers
    # skip tables without geometry (e.g. QGIS layer styles)
    non_spatial = [layer for layer in layers if data_source.GetLayerByName(layer).GetGeomType() == ogr.wkbNone]
    if non_spatial:
        h.log(f"skipping tables without geometry: {', '.join(non_spatial)}")
    layers = [layer for layer in layers if layer not in non_spatial]
    layers_geometry_types = set(data_source.GetLayerByName(layer).GetGeomType() for layer in layers)
    is_gpkg = data_source.GetDriver().GetName() == "GPKG"

    # ID column of the target table: if the input data has an attribute with the same name (e.g. 'fid' in merged datasets),
    # its values would be used as IDs (possibly not unique) - use a different name for the ID column instead
    fid = fid or "fid"
    field_names = {data_source.GetLayerByName(layer).GetLayerDefn().GetFieldDefn(i).GetName().lower()
                   for layer in layers for i in range(data_source.GetLayerByName(layer).GetLayerDefn().GetFieldCount())}
    if fid.lower() in field_names:
        h.log(f"input data contains an attribute '{fid}' - using 'import_fid' as ID column of table '{table}'")
        fid = "import_fid"
    fid = f"-lco FID={fid}"
    transform = f"-t_srs EPSG:{target_srid}" if target_srid else ""
    geometry_type = "-nlt GEOMETRY" if len(layers_geometry_types) > 1 else ""
    # spatial filter (min lon, min lat, max lon, max lat) - uses the spatial index of the input file
    spatial_filter = f"-spat {' '.join(str(v) for v in extent)} -spat_srs EPSG:4326" if extent else ""

    for layer in layers:
        h.log(f"import layer \"{layer}\"")
        geometry_column = data_source.GetLayerByName(layer).GetGeometryColumn()

        select = f"-select \"{attributes}\"" if attributes else ""
        conditions = []
        if is_gpkg and geometry_column:
            # skip empty geometries (e.g. polygons with empty rings) - these can crash the PostGIS backend on insert
            conditions.append(f"ST_IsEmpty({geometry_column}) = 0")
        if geometry_types:
            conditions.append(f"ST_GeometryType({geometry_column}) IN ({geometry_types})")
        where = f"-where \"{' AND '.join(conditions)}\"" if conditions else ""
        
        result = subprocess.run(f"ogr2ogr -f PostgreSQL \"PG:{connection_string}\" {fid} -skipfailures -lco GEOMETRY_NAME=geom -nln {schema}.{table} {transform} {geometry_type} {spatial_filter} {select} {where} \"{path}\" \"{layer}\"", 
            shell=True, check=True)
        h.debugLog(f"ogr2ogr returned code: {result.returncode}")
        #h.debugLog(f"ogr2ogr stdout: {result.args}")


def import_osm(connection_string: str, path: str, path_config: str, schema: str, prefix: str = None) -> None:
    """Takes in a path to an OSM file (pbf / xml) and imports it to database tables using the flex output of osm2pgsql
    (Lua configuration 'path_config' - defines the tables). The prefix applies to the middle tables (slim mode: stored in
    the database instead of memory), which osm2pgsql drops after the import (--drop)."""
    prefix = f"--prefix {prefix}" if prefix else ""
    # osm2pgsql output: warnings and progress (also if the output is redirected, e.g. to a file); all details from log level 3 on
    log_level = "info" if h.get_current_log_level() >= h.LOG_LEVEL_3_DETAILED else "warn"
    h.info(f"importing OSM data from '{path}'")
    subprocess.run(f"osm2pgsql --log-level={log_level} --log-progress=true --database={connection_string} --schema={schema} --middle-schema={schema} {prefix} --slim --drop --output=flex --style=\"{path_config}\" \"{path}\"",
        shell=True, check=True)


def extract_osm(path_in: str, path_out: str, bbox: tuple) -> None:
    """Extracts a bounding box (min_lon, min_lat, max_lon, max_lat) from an OSM file using osmium.
    Strategy 'smart' keeps ways and multipolygon relations complete (also beyond the bounding box)."""
    bbox_str = ",".join(str(v) for v in bbox)
    h.info(f"extracting OSM subset from '{path_in}'")
    subprocess.run(f"osmium extract --bbox {bbox_str} --strategy smart --overwrite --output=\"{path_out}\" \"{path_in}\"",
        shell=True, check=True)


def get_stored_aoi_srid(db_settings: DbSettings):
    """Returns the target SRID stored with the AOI of the current case (determined during a previous import), if any."""
    db = PostgresConnection.from_settings_object(db_settings)
    try:
        db.connect()
    except Exception as e:
        h.log(f"could not connect to the database to read the target SRID of the AOI: {e}")
        return None
    try:
        aoi_table = f"{db_settings.entities.data_schema}.{db_settings.entities.table_aoi}"
        if not db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (aoi_table,))[0]:
            return None
        row = db.query_one(f"SELECT srid FROM {aoi_table} WHERE name = %s;", (GlobalSettings.case_id,))
        return row[0] if row else None
    except Exception as e:
        h.log(f"could not read the target SRID from the AOI table: {e}")
        return None
    finally:
        db.close()


class GipImporter(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict):
        h.info('importing gip')
        h.log(f"using import settings: {str(settings)}")
        if h.has_keys(settings, ['filename_A']) and not h.has_keys(settings, ['filename']):
            h.majorInfo("error: the import setting 'filename_A' was renamed to 'filename'. Please update your settings file.")
            sys.exit(1)
        h.require_keys(settings, ['filename'], "error: GIP import requires the key 'filename' (zip file of the GIP export) in the import section.")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        files_A = [
            {'filename': 'BikeHike.txt', 'table': 'gip_bikehike', 'columns': ['use_id']},
            {'filename': 'Link.txt', 'table': 'gip_link', 'columns': ['link_id']},
            {'filename': 'LinkCoordinate.txt', 'table': 'gip_linkcoordinate', 'columns': ['link_id', 'count']},
            {'filename': 'LinkUse.txt', 'table': 'gip_linkuse', 'columns': ['use_id']},
            {'filename': 'Link2ReferenceObject.txt', 'table': 'gip_link2referenceobject', 'columns': ['idseq']},
            {'filename': 'Node.txt', 'table': 'gip_node', 'columns': ['node_id']},
            {'filename': 'ReferenceObject.txt', 'table': 'gip_referenceobject', 'columns': ['refobj_id']},
        ]

        # open database connection
        h.debugLog('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.init_extensions_and_schema(schema)

        # extract zip files
        h.logBeginTask('extract zip files')
        with zipfile.ZipFile(os.path.join(directory, settings['filename']), 'r') as zf:
            for file in files_A:
                if not os.path.isfile(os.path.join(directory, os.path.splitext(settings['filename'])[0], file['filename'])):
                    zf.extract(file['filename'], os.path.join(directory, os.path.splitext(settings['filename'])[0]))
        h.logEndTask()

        # create tables from files_A
        for file in files_A:
            h.logBeginTask(f"create table \"{file['table']}\"")
            if not os.path.isfile(os.path.join(directory, os.path.splitext(settings['filename'])[0], f"{os.path.splitext(file['filename'])[0]}.csv")):
                create_csv(os.path.join(directory, os.path.splitext(settings['filename'])[0], file['filename']))
            if not os.path.isfile(os.path.join(directory, os.path.splitext(settings['filename'])[0], f"{os.path.splitext(file['filename'])[0]}.sql")):
                create_sql(os.path.join(directory, os.path.splitext(settings['filename'])[0], file['filename']))

            db.drop_table(file['table'], schema=schema)
            db.execute_sql_from_file(f"{os.path.splitext(file['filename'])[0]}", os.path.join(directory, os.path.splitext(settings['filename'])[0]))
            db.commit()

            import_csv(db.connection_string, os.path.join(directory, os.path.splitext(settings['filename'])[0], f"{os.path.splitext(file['filename'])[0]}.csv"), schema, table=file['table'])

            db.add_primary_key(file['table'], file['columns'], schema=schema)
            db.commit()
            h.logEndTask()

        # close database connection
        h.debugLog('closing database connection')
        db.close()


GIP2_IMPORT_TABLES = [
    {'name': 'NODE', 'table': 'gip2_node', 'pk': ['short_id']},
    {'name': 'LINK', 'table': 'gip2_link', 'pk': ['short_id'], 'indexes': [['node_from_short_id'], ['node_to_short_id']]},
    {'name': 'LINK_COORDINATE', 'table': 'gip2_linkcoordinate', 'pk': ['object_id'], 'indexes': [['link_short_id', 'sequence']]},
    {'name': 'LINEAR_USE_PART', 'table': 'gip2_linear_use_part', 'pk': ['short_id'], 'indexes': [['link_short_id']]},
    {'name': 'BIKE_HIKE', 'table': 'gip2_bikehike', 'pk': ['short_id']},
    {'name': 'REFERENCE_OBJECT', 'table': 'gip2_referenceobject', 'pk': ['short_id']},
    {'name': 'LINK_2_REFERENCE_OBJECT', 'table': 'gip2_link2referenceobject', 'pk': ['short_id'], 'indexes': [['link_short_id'], ['reference_object_id']]},
]

GIP2_IDF_TYPE_MAP = {
    'uuid': 'uuid',
    'integer': 'integer',
    'double': 'double precision',
    'text': 'text',
}

GIP2_SQL_RESERVED = {'offset': 'offset_'}


def _gip2_sql_type(frm: str) -> str:
    """Map a GIP 2.0 IDF format token to a PostgreSQL type."""
    frm = frm.strip().lower()
    if frm in GIP2_IDF_TYPE_MAP:
        return GIP2_IDF_TYPE_MAP[frm]
    if frm == 'string':
        return 'varchar'
    if m := re.search(r"^(string)[(]([0-9]*)[)]", frm):
        return f"varchar({m.group(2)})"
    if m := re.search(r"^(decimal)[(]([0-9]*)[,]([0-9]*)[)]", frm):
        return f"numeric({m.group(2)},{m.group(3)})"
    if m := re.search(r"^(decimal)[(]([0-9]*)[)]", frm):
        precision = int(m.group(2))
        if precision <= 4:
            return "smallint"
        if precision <= 10:
            return "integer"
        if precision <= 18:
            return "bigint"
        return f"numeric({precision})"
    return frm


def _gip2_column_name(name: str) -> str:
    name = name.strip().lower()
    return GIP2_SQL_RESERVED.get(name, name)


def create_gip2_sql(table: str, attributes: List[str], formats: List[str], sql_path: str) -> None:
    """Write a CREATE TABLE statement for a GIP 2.0 IDF table."""
    columns = [f"{_gip2_column_name(atr)} {_gip2_sql_type(frm)}" for atr, frm in zip(attributes, formats)]
    with open(sql_path, 'w', encoding='utf-8') as file_sql:
        file_sql.write(f"CREATE TABLE {table} ({', '.join(columns)});")


def _gip2_csv_record(line: str) -> str:
    """Strip the IDF rec; prefix and turn empty quoted fields into COPY NULLs."""
    return line[4:].replace('""', '').replace('" "', '')


def split_gip2_idf(idf_path: str, output_dir: str, tables: List[dict]) -> None:
    """Stream-split a GIP 2.0 routingexport IDF into per-table CSV + SQL files."""
    wanted = {item['name']: item for item in tables}
    os.makedirs(output_dir, exist_ok=True)

    current_name = None
    csv_file = None
    attributes = None
    formats = None
    record_count = 0

    def close_current():
        nonlocal csv_file, record_count
        if csv_file is not None:
            csv_file.close()
            csv_file = None
            h.log(f"wrote {record_count} records for {current_name}")
        record_count = 0

    try:
        with open(idf_path, 'r', encoding='utf-8-sig') as idf:
            for line in idf:
                if line.startswith('tbl;'):
                    close_current()
                    current_name = line[4:].strip()
                    attributes = None
                    formats = None
                    continue

                if current_name not in wanted:
                    continue

                item = wanted[current_name]
                stem = current_name.lower()
                csv_path = os.path.join(output_dir, f"{stem}.csv")
                sql_path = os.path.join(output_dir, f"{stem}.sql")

                if line.startswith('atr;'):
                    attributes = line[4:].strip().split(';')
                    csv_file = open(csv_path, 'w', encoding='utf-8')
                    csv_file.write(';'.join(_gip2_column_name(atr) for atr in attributes) + '\n')
                elif line.startswith('frm;'):
                    formats = line[4:].strip().split(';')
                    if attributes is None:
                        raise Exception(f"GIP 2.0 table '{current_name}' is missing an atr; line before frm;")
                    create_gip2_sql(item['table'], attributes, formats, sql_path)
                elif line.startswith('rec;'):
                    if csv_file is None:
                        raise Exception(f"GIP 2.0 table '{current_name}' is missing an atr; line before rec;")
                    csv_file.write(_gip2_csv_record(line))
                    record_count += 1
    finally:
        close_current()


def resolve_gip2_idf_path(directory: str, filename: str) -> str:
    """Resolve a GIP 2.0 zip or txt path to the IDF file, extracting the zip if needed."""
    source_path = os.path.join(directory, filename)
    if not os.path.exists(source_path):
        raise Exception(f"The provided GIP 2.0 input file could not be found: '{source_path}'")

    if filename.lower().endswith('.txt'):
        return source_path

    if filename.lower().endswith('.zip'):
        stem = os.path.splitext(filename)[0]
        sibling_txt = os.path.join(directory, stem + '.txt')
        if os.path.isfile(sibling_txt):
            h.log(f"using already extracted IDF '{sibling_txt}'")
            return sibling_txt

        extract_dir = os.path.join(directory, stem)
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(source_path, 'r') as zf:
            txt_members = [name for name in zf.namelist() if name.lower().endswith('.txt')]
            if not txt_members:
                raise Exception(f"No .txt IDF found inside '{source_path}'")
            member = txt_members[0]
            extracted = os.path.join(extract_dir, os.path.basename(member))
            if not os.path.isfile(extracted):
                h.log(f"extracting '{member}' from '{filename}'")
                source = zf.open(member)
                try:
                    with open(extracted, 'wb') as target:
                        while True:
                            chunk = source.read(1024 * 1024 * 8)
                            if not chunk:
                                break
                            target.write(chunk)
                finally:
                    source.close()
            return extracted

    raise Exception(f"GIP 2.0 import expects a .zip or .txt file, got '{filename}'")


class Gip2Importer(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict):
        h.info('importing gip 2.0')
        h.log(f"using import settings: {str(settings)}")
        if h.has_keys(settings, ['filename_A']) and not h.has_keys(settings, ['filename']):
            h.majorInfo("error: the import setting 'filename_A' was renamed to 'filename'. Please update your settings file.")
            sys.exit(1)
        h.require_keys(settings, ['filename'], "error: GIP 2.0 import requires the key 'filename' (zip file of the GIP 2.0 export) in the import section.")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory
        filename = settings['filename']

        # open database connection
        h.debugLog('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.init_extensions_and_schema(schema)

        h.logBeginTask('resolve GIP 2.0 IDF')
        idf_path = resolve_gip2_idf_path(directory, filename)
        tables_dir = os.path.join(directory, os.path.splitext(os.path.basename(filename))[0] + '_tables')
        h.log(f"IDF: {idf_path}")
        h.log(f"split directory: {tables_dir}")
        h.logEndTask()

        h.logBeginTask('split GIP 2.0 IDF into tables')
        missing = [
            item for item in GIP2_IMPORT_TABLES
            if not os.path.isfile(os.path.join(tables_dir, f"{item['name'].lower()}.csv"))
            or not os.path.isfile(os.path.join(tables_dir, f"{item['name'].lower()}.sql"))
        ]
        if missing:
            h.log(f"creating CSV/SQL for: {', '.join(item['name'] for item in missing)}")
            # Always rewrite all required tables together so a partial previous split cannot mix versions
            split_gip2_idf(idf_path, tables_dir, GIP2_IMPORT_TABLES)
        else:
            h.log('CSV/SQL files already exist, skipping split')
        h.logEndTask()

        for item in GIP2_IMPORT_TABLES:
            h.logBeginTask(f"create table \"{item['table']}\"")
            stem = item['name'].lower()
            db.drop_table(item['table'], schema=schema)
            db.execute_sql_from_file(stem, tables_dir)
            db.commit()

            import_csv(
                db.connection_string,
                os.path.join(tables_dir, f"{stem}.csv"),
                schema,
                table=item['table']
            )

            db.add_primary_key(item['table'], item['pk'], schema=schema)
            for columns in item.get('indexes', []):
                db.add_index(item['table'], columns, schema=schema)
            db.commit()
            h.logEndTask()

        h.debugLog('closing database connection')
        db.close()


def bbox_area_km2(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> float:
    """Returns the area (km²) of a bounding box given in WGS84 (on a sphere with the mean earth radius)."""
    r = 6371.0088
    return r * r * math.radians(max_lon - min_lon) * (math.sin(math.radians(max_lat)) - math.sin(math.radians(min_lat)))


class OsmImporter(DbStep):
    # used as optional importer (e.g. for GIP): only OSM files are supported (no AOI / download) - see run_optional_importers
    optional: bool = False
    # optional importer: extent of the network incl. margin (min lon, min lat, max lon, max lat) the OSM file is clipped to; None: no clipping
    network_extent: tuple = None

    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def _get_srid_for_AOI(self, data_con:PostgresConnection, aoi_name: str, aoi_table: str = "aoi", aoi_schema: str = "data", save_to_aoi_table: bool = True) -> int:
        data_con.execute_sql_from_file("determine_utmzone", "sql/functions")
        srid = data_con.query_one(f"SELECT srid FROM {aoi_schema}.{aoi_table} WHERE name=%s", (aoi_name,))[0]
        if srid is None:
            srid = data_con.query_one(f"SELECT utmzone(ST_Centroid(geom)) FROM {aoi_schema}.{aoi_table} WHERE name=%s", (aoi_name,))[0]
            h.log(f"determined SRID based on AOI centroid: EPSG:{srid}")
            if save_to_aoi_table:
                self._save_srid_for_AOI(srid, data_con, aoi_name, aoi_table, aoi_schema)
        else:
            h.log(f"fetched SRID from AOI table: EPSG:{srid}")
        return srid
    
    def _save_srid_for_AOI(self, srid: int, data_con:PostgresConnection, aoi_name: str, aoi_table: str = "aoi", aoi_schema: str = "data"):
        data_con.ex(f"UPDATE {aoi_schema}.{aoi_table} SET srid=%s WHERE name=%s", (srid, aoi_name,))
        data_con.commit()

    def _load_osm_aoi_from_placename(self, db: PostgresConnection, data_schema: str, settings: dict):
        # db settings
        # first, set target schema
        db.schema = data_schema
        aoi_table = self.db_settings.entities.table_aoi
        aoi_name = GlobalSettings.case_id

        # download AOI
        # first: create AOI query string
        h.debugLog(f"starting AOI query for '{settings['place_name']}'")
        # use geopy and OSM Nominatim API to query polygon features based on the given place name
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="py_NetAScore_downloader")
        location = geolocator.geocode(settings['place_name'], geometry="wkt", exactly_one=False)
        import geopandas as gpd
        records = [l.raw for l in location]
        d = gpd.GeoDataFrame(records, geometry=gpd.GeoSeries.from_wkt([r["geotext"] for r in records]), crs="EPSG:4326")
        # filter for polygon features / (admin) boundaries; highest importance first
        df = d[d["class"]=="boundary"].sort_values(by="importance", ascending=False)
        areas = gpd.GeoDataFrame(df, geometry="geometry")
        # check results
        num_ft = len(areas)
        if num_ft < 1:
            h.majorInfo("ERROR: no matching feature found. Please try again with different AOI query settings.")
            raise Exception("AOI not found. Please check your query settings or use a bounding box instead (parameter 'bbox' in 'import' section of settings file).")
        # by default, use the first result (in case there were more results returned)
        fid = 0 
        if num_ft > 1:
            h.info(f"Found {num_ft} matching features:")
            i = 0
            for _id, ft in areas.iterrows():
                i+=1
                print(f"{i}: {ft.addresstype} \t {ft.display_name}")
            if h.has_keys(settings, ['interactive']) and settings['interactive']:
                # let user choose which result to use if more than one AOI was found
                fid = int(input("Which one do you want to use? [1.." + str(i) + "] for your choice, other number to abort:\t"))
                if not fid in range(i+1) or fid < 1:
                    print("You chose to abort the process. Will now exit.")
                    exit("User cancelled processing during AOI choice")
                print("You chose to continue with AOI #", fid)
                fid -= 1 # back to 0-based index value
            else:
                h.info("Using the first search result. If you want to use a different AOI, either provide more query parameters or add 'interactive: True' to the import settings for an interactive choice.")
        # selected AOI
        h.logBeginTask("importing AOI to db table...")
        area = areas.iloc[fid]
        h.info(f"continuing with AOI: {area.addresstype} '{area.display_name}'")
        # extract largest single-polygon in case of Multi-Polygon input
        area_geom = None
        if area.geometry.geom_type == "MultiPolygon":
            h.debugLog(f"AOI is MultiPolygon consisting of {len(area.geometry.geoms)} geometries:")
            polys = gpd.GeoDataFrame.from_records([[g.area, g] for g in area.geometry.geoms], columns=["area", "geometry"])
            pgdf = gpd.GeoDataFrame(polys.sort_values(by="area", ascending=False), geometry="geometry", crs="EPSG:4326")
            area_geom = pgdf.iloc[0].geometry
        else:
            area_geom = area.geometry
        h.debugLog("Polygon WKT: " + str(area_geom))
        db.ex("INSERT INTO " + aoi_table + " (name, geom) VALUES (%s, ST_GeomFromText(%s::text,4326));", (aoi_name, str(area_geom)))
        db.commit()
        h.logEndTask()

    def _set_aoi_from_geodata(self, filepath:str, db: PostgresConnection, data_schema: str, settings: dict):
        import geopandas as gpd
        # db settings
        # first, set target schema
        db.schema = data_schema
        aoi_table = self.db_settings.entities.table_aoi
        aoi_name = GlobalSettings.case_id
        if not os.path.exists(filepath):
            raise Exception(f"Provided AOI input file path does not exist: '{filepath}'")
        df:gpd.GeoDataFrame = gpd.GeoDataFrame.from_file(filepath)
        h.info(f"Loaded AOI input file. Found {len(df)} features.")
        # the AOI is stored in WGS84 (EPSG:4326)
        if df.crs is None:
            raise Exception(f"The AOI input file '{filepath}' has no coordinate system. Please define the coordinate system of the file.")
        df = df.to_crs(4326)
        # find feature with matching AOI caseID or join all polygons
        geom = None
        if len(df) < 1:
            raise Exception("No features found in provided AOI input file. Please provide at least one input geometry.")
        elif len(df) > 1:
            # enable filtering e.g. by name/ID column (match caseID of NetAScore)
            if "name" in df.columns:
                dff = df[df["name"]==aoi_name]
                if len(dff) > 0:
                    geom = dff.geometry.union_all()
            if geom is None or geom.is_empty:
                geom = df.geometry.union_all()
        else: 
            geom = df.iloc[0].geometry
        # generate AOI entry and insert geometry into AOI table
        db.ex("INSERT INTO " + aoi_table + " (name, geom) VALUES (%s, ST_GeomFromText(%s,4326));", (aoi_name, str(geom)))

    def _set_srid_for_aoi(self, db: PostgresConnection, data_schema: str):
        db.schema = data_schema
        aoi_table = self.db_settings.entities.table_aoi
        aoi_name = GlobalSettings.case_id
        # determine SRID if not specified manually
        srid = GlobalSettings.custom_srid
        if srid is None:
            srid = self._get_srid_for_AOI(db, aoi_name, aoi_table, data_schema)
            GlobalSettings.default_srid = srid
        else:
            # save cusom SRID to AOI table
            self._save_srid_for_AOI(srid, db, aoi_name, aoi_table, data_schema)

    def _get_extract_bbox(self, db: PostgresConnection, data_schema: str, settings: dict, margin: int = 200) -> tuple:
        """Returns the bounding box (min_lon, min_lat, max_lon, max_lat) of the clipping area (see 'osm_network' template),
        extended by a margin (in m) to include surrounding features (e.g. buildings, greenness) for edges at its boundary."""
        aoi_table = self.db_settings.entities.table_aoi
        srid = GlobalSettings.get_target_srid()
        buffer = settings['buffer'] if h.has_keys(settings, ['buffer']) else 0
        return db.query_one(f"""
            WITH clip_area AS (
                SELECT CASE
                           WHEN %(clip_mode)s = 'aoi' THEN ST_Buffer(ST_Transform(geom, %(srid)s), %(buffer)s)
                           ELSE ST_SetSRID(ST_Expand(box2d(ST_Transform(geom, %(srid)s)), %(buffer)s), %(srid)s)
                       END AS geom
                FROM {data_schema}.{aoi_table}
                WHERE name = %(aoi_name)s
            ), extract_area AS (
                SELECT ST_Transform(ST_SetSRID(ST_Expand(box2d(geom), %(margin)s), %(srid)s), 4326) AS geom
                FROM clip_area
            )
            SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) FROM extract_area;""",
            {'clip_mode': h.get_clip_mode(settings), 'srid': srid, 'buffer': buffer, 'margin': margin, 'aoi_name': GlobalSettings.case_id})

    def _load_osm_data_for_aoi(self, db: PostgresConnection, data_schema: str, settings: dict):
        # db settings
        # first, set target schema
        db.schema = data_schema
        aoi_table = self.db_settings.entities.table_aoi
        aoi_name = GlobalSettings.case_id

        srid = GlobalSettings.get_target_srid()

        # get BBox for network coverage (larger than chosen AOI -> prevent edge effects)
        buffer = 0
        if h.has_keys(settings, ['buffer']):
            buffer = settings['buffer']
        bbox = db.query_one("WITH a as (SELECT ST_Transform(ST_setSRID(ST_EXPAND(box2d(ST_Transform(geom, %s)),%s),%s), 4326) as bbox FROM " + 
                                    aoi_table + """ WHERE name=%s) 
                                    SELECT ST_YMIN(bbox), ST_XMIN(bbox), ST_YMAX(bbox), ST_XMAX(bbox) FROM a;""", 
                                    (srid, buffer, srid, aoi_name,)
                                )
        h.debugLog(f"Determined Bounding box: {bbox}")
        # load OSM data from bounding box
        self._load_osm_data_from_bbox(bbox, settings)

    def _check_download_area(self, bbox: tuple, settings: dict):
        """Ensures that the Overpass API is only queried for small areas: larger areas require an OSM extract (e.g. Geofabrik)."""
        max_area = float(settings.get('max_download_area') or GlobalSettings.overpass_max_area)
        area = bbox_area_km2(*bbox)
        h.log(f"area of the OSM download: {area:.0f} km² (maximum: {max_area:.0f} km²)")
        if area <= max_area:
            return
        h.majorInfo(f"ERROR: the area of the OSM download ({area:.0f} km²) exceeds the maximum area for Overpass API downloads ({max_area:.0f} km²).\n"
                    "Please download an OSM extract covering your area of interest (e.g. from https://download.geofabrik.de), "
                    "save it to the data directory and add it to the 'import' section of your settings file:\n"
                    "    filename: my_extract.osm.pbf   #(replace with actual filename)\n"
                    "  Keep 'place_name', 'bbox', or 'aoi_filename' to clip the extract to your area of interest.\n"
                    "  The maximum area can be changed with the import setting 'max_download_area' (in km²) - large downloads may fail or overload the Overpass API servers.")
        raise Exception("OSM download area too large for the Overpass API. Terminating.")

    def _load_osm_data_from_bbox(self, bbox: tuple, settings: dict):
        """Downloads OSM data for the bounding box (min_lat, min_lon, max_lat, max_lon) from the Overpass API."""
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-agent', GlobalSettings.overpass_api_user)]
        urllib.request.install_opener(opener)
        q_template: str = """
            [timeout:180];
            nwr[!"boundary"][!"place"][!power]["route"!="bus"]["route"!="road"]["route"!="ferry"]["route"!="power"]["route"!="train"]["route"!="railway"](__bbox__);
            (._;>;);
            out;"""
        net_file = f"{GlobalSettings.osm_download_prefix}_{GlobalSettings.case_id}.xml"
        file_exists = os.path.isfile(os.path.join(GlobalSettings.data_directory, net_file))
        if file_exists:
            on_existing = h.normalize_on_existing(settings.get('on_existing'), "section 'import'", default='abort')
            if on_existing in ('reuse', 'reuse_or_overwrite'):
                h.info("Target file for OSM download already exists. Skipping download (re-using existing file). You can change this behavior with the import setting 'on_existing'. [reuse/reuse_or_overwrite/overwrite/abort]")
                return
            if on_existing != 'overwrite':
                raise Exception("Target file for OSM download already exists. Aborting. Please resolve the conflict manually or specify a different value for 'on_existing' in the import settings. [reuse/reuse_or_overwrite/overwrite/abort]")
        self._check_download_area(bbox, settings)
        if file_exists:
            h.info("Target file for OSM download already exists. Deleting existing file and proceeding with download. You can change this behavior with the import setting 'on_existing'. [reuse/reuse_or_overwrite/overwrite/abort]")
        q_str = q_template.replace("__bbox__", ",".join(str(v) for v in bbox))
        h.debugLog(f"prepared OSM overpass API query: \n'{q_str}")

        h.logBeginTask("Starting OSM data download...")
        target = os.path.join(GlobalSettings.data_directory, net_file)
        endpoints = GlobalSettings.overpass_api_endpoints
        failures = []
        success = False
        for i, endpoint in enumerate(endpoints):
            error = None
            try:
                file_name, headers = urllib.request.urlretrieve(endpoint + "?data=" + urllib.parse.quote_plus(q_str), target)
            except HTTPError as e:
                error = f"HTTP status {e.code} ({e.reason})"
                h.debugLog(f"Response headers from '{endpoint}': {e.headers}")
                try:
                    h.debugLog(f"Response from '{endpoint}': {e.read(2000).decode('utf-8', errors='replace')}")
                except Exception:
                    pass
            except KeyboardInterrupt:
                h.majorInfo(f"OSM download from '{endpoint}' interrupted by user. Terminating.")
                _remove_file(target)
                exit()
            except BaseException as e:
                error = f"{type(e).__name__}: {e}"
            else:
                h.debugLog(f"Response headers from '{endpoint}': {headers}")
                # the Overpass API reports errors during query execution (e.g. timeout, out of memory) as remark in the
                # response (HTTP status 200) - the data is incomplete in this case
                error = _overpass_response_error(target)
            if error is None:
                success = True
                h.info(f"OSM download from '{endpoint}' succeeded.")
                break
            failures.append(f"{endpoint}: {error}")
            _remove_file(target)  # no incomplete downloads (would be re-used by the next run)
            next_try = " - trying the next API endpoint" if i + 1 < len(endpoints) else ""
            h.majorInfo(f"WARNING: OSM download from '{endpoint}' failed ({i + 1} of {len(endpoints)} API endpoints): {error}{next_try}")
        if not success:
            h.majorInfo("ERROR: OSM data download failed for all Overpass API endpoints:\n  " + "\n  ".join(failures))
            h.majorInfo("The Overpass API servers may be overloaded - please try again later. Alternatively, download an OSM extract "
                        "covering your area of interest (e.g. from https://download.geofabrik.de), save it to the data directory and "
                        "add it to the 'import' section of your settings file:\n"
                        "    filename: my_extract.osm.pbf   #(replace with actual filename)\n"
                        "  Keep 'place_name', 'bbox', or 'aoi_filename' to clip the extract to your area of interest.")
            raise Exception("OSM data download was not successful. Terminating.")
        h.logEndTask()

    def run_step(self, settings: dict):
        h.info('importing osm')
        h.log(f"using settings: {str(settings)}")
        use_overpass_api: bool = False

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory
        reuse_aoi = False

        # open database connection
        h.debugLog('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)
        ### init AOI table 
        # prepare DB: create schema and setup extensions
        db.create_schema(schema)
        # first, set target schema
        db.schema = schema
        aoi_table = self.db_settings.entities.table_aoi
        aoi_name = GlobalSettings.case_id
        on_existing = h.normalize_on_existing(settings.get('on_existing'), "section 'optional' > 'osm'" if self.optional else "section 'import'", default='reuse')
        # create AOI table if it not already exists
        db.ex(f"""CREATE TABLE IF NOT EXISTS {aoi_table} (
            id    serial NOT NULL PRIMARY KEY,
            name  varchar(40) NOT NULL CHECK (name <> '') UNIQUE,
            geom  geometry,
            srid  integer
        );""")

        # an AOI (bbox, AOI file, or place name) is required for OSM download; for OSM file imports it is optional and
        # (if given) used for clipping the network to the area of interest (see import setting 'clip')
        # (optional importer: OSM file only - clipped to the network extent, if given)
        has_aoi = not self.optional and h.has_any_key(settings, ['place_name', 'bbox', 'aoi_filename'])
        if not h.has_keys(settings, ['filename']):
            h.info("no OSM file provided. Checking for OSM query settings instead...")
            if not has_aoi:
                raise Exception("neither 'place_name', 'aoi_filename', nor 'bbox' parameter specified for OSM download. Terminating.")
            use_overpass_api = True
        else:
            h.info("using existing OSM file for import step.")

        # clipping to the area of interest (requires an AOI and osmium)
        clip = has_aoi and h.get_clip_mode(settings) != 'none'
        clip_network = self.optional and self.network_extent is not None
        if (clip or clip_network) and shutil.which('osmium') is None:
            raise Exception("osmium is required for clipping OSM data to the area of interest, but was not found. "
                            "Please install osmium-tool (e.g. 'conda install -c conda-forge osmium-tool') or set the import setting 'clip: none'.")

        if has_aoi:
            ### handle conflicts (existing AOI entry with same caseID)
            # check whether an AOI with the given name already exists
            excnt = db.query_one("SELECT COUNT(*) FROM " + aoi_table + " WHERE name = %s;", (aoi_name,))[0]
            if excnt > 0:
                h.info(f"found {excnt} entry in existing AOI table with the given AOI name '{aoi_name}'")
                # if exists, use param switch or ask whether to use an existing AOI or overwrite it
                if  on_existing == 'overwrite':
                    h.info("...you specified to overwrite the existing AOI entry.")
                    # delete existing AOI from AOI table
                    db.ex("DELETE FROM " + schema + "." + aoi_table + " WHERE name = %s;", (aoi_name,))
                    # continue script execution
                elif on_existing in ('reuse', 'reuse_or_overwrite'):
                    # only the AOI query is skipped - the OSM download reuses an existing download file (see _load_osm_data_from_bbox),
                    # otherwise it is downloaded for the existing AOI (e.g. if a previous run failed before or during the download)
                    h.info("...you chose to re-use the existing AOI entry. Skipping AOI download.")
                    reuse_aoi = True
                else:
                    raise Exception("An AOI with the given id already exists. Please resolve the conflict manually or provide a different option for the import setting 'on_existing': [reuse/reuse_or_overwrite/overwrite/abort]")
            else:
                h.info("AOI name '" + aoi_name + "' is not in use -> continuing with AOI download...")

            ### import / query AOI and add it to AOI table
            if not reuse_aoi:
                if h.has_keys(settings, ['bbox']):               # import from bounding box
                    bx = h.parse_bbox(settings['bbox'])  # min lat, min lon, max lat, max lon
                    bbox_geom = f"st_setSRID(st_envelope(st_makeLine(st_makePoint({bx[1]},{bx[0]}), st_makePoint({bx[3]},{bx[2]}))), 4326)"
                    db.ex("INSERT INTO " + aoi_table + " (name, geom) VALUES (%s," + bbox_geom + ");", (aoi_name,))
                elif h.has_keys(settings, ['aoi_filename']):     # import from given AOI polygon (geopackage file)
                    filepath = os.path.join(directory, str(settings['aoi_filename']).strip())
                    self._set_aoi_from_geodata(filepath, db, schema, settings)
                elif h.has_keys(settings, ['place_name']):       # import from place name
                    self._load_osm_aoi_from_placename(db, schema, settings)

            # determine target SRID based on the AOI (unless specified manually)
            self._set_srid_for_aoi(db, schema)

            # finally, query OSM data based on previously defined AOI (an existing download file is reused depending on 'on_existing')
            if use_overpass_api:
                self._load_osm_data_for_aoi(db, schema, settings)

        # import osm file
        h.logBeginTask('import osm file')
        db.drop_table("osm_point", schema=schema)
        db.drop_table("osm_line", schema=schema)
        db.drop_table("osm_polygon", schema=schema)
        db.drop_table("osm_bicycle_route", schema=schema)
        db.drop_table("osm_nodes", schema=schema)
        db.drop_table("osm_rels", schema=schema)
        db.drop_table("osm_roads", schema=schema)  # still created by earlier osm2pgsql imports (before NetAScore 2.0.0)
        db.drop_table("osm_ways", schema=schema)
        db.commit()

        filename = f"{GlobalSettings.osm_download_prefix}_{GlobalSettings.case_id}.xml"
        if not use_overpass_api:
            filename = settings['filename']
        osm_path = os.path.join(directory, filename)
        source_path = osm_path

        # if the network is clipped to the AOI, only import the relevant part of the OSM data
        extract_path = None
        bbox = None
        if clip:
            bbox = self._get_extract_bbox(db, schema, settings)
            h.log(f"extracting OSM data for bounding box {bbox}")
            extract_path = os.path.join(directory, f"{GlobalSettings.osm_download_prefix}_{GlobalSettings.case_id}_extract.osm.pbf")
            extract_osm(osm_path, extract_path, bbox)
            osm_path = extract_path
        elif clip_network:
            bbox = tuple(self.network_extent)
            h.log(f"extracting OSM data for the network extent {bbox}")
            extract_path = os.path.join(directory, f"{GlobalSettings.osm_download_prefix}_{GlobalSettings.case_id}_extract.osm.pbf")
            extract_osm(osm_path, extract_path, bbox)
            osm_path = extract_path

        import_osm(db.connection_string, osm_path, os.path.join('resources', 'osm2pgsql_flex.lua'), schema, prefix='osm')  # 12 m 35 s
        if extract_path:
            os.remove(extract_path)
        h.logEndTask()

        # datasets derived from OSM data are recorded in the dataset registry (shared data schema) - these are reused
        # (depending on 'on_existing') if they were created from the same OSM data with the same settings
        osm_source = registry.file_signature(source_path)
        # settings defining the spatial extent (normalized, so that e.g. a default value and the same value given explicitly equal)
        osm_options = {key: str(settings[key]).strip() for key in ['place_name', 'aoi_filename'] if settings.get(key) is not None}
        if settings.get('bbox') is not None:
            osm_options['bbox'] = h.parse_bbox(settings['bbox'])
        if has_aoi:
            osm_options['buffer'] = float(settings.get('buffer') or 0)
            osm_options['clip'] = h.get_clip_mode(settings)
        if clip_network:
            osm_options['clip'] = 'network'
            osm_options['extent'] = [round(v, 5) for v in bbox]
        osm_coverage = None
        if bbox is None:  # coverage: extent of the imported OSM data (otherwise: extracted area)
            osm_coverage = db.query_one(f"""SELECT ST_AsText(ST_SetSRID(ST_Extent(way)::geometry, 4326)) FROM (
                SELECT way FROM {schema}.osm_point UNION ALL SELECT way FROM {schema}.osm_line UNION ALL SELECT way FROM {schema}.osm_polygon) t;""")[0]

        # create dataset "building"
        h.logBeginTask('create dataset "building"')
        if registry.prepare_import(db, schema, 'building', ['building'], on_existing, osm_source, osm_options):
            db.execute('''
                CREATE TABLE building AS ( -- 16 s
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Polygon, %(target_srid)s) AS geom
                    FROM osm_polygon
                    WHERE building IS NOT NULL
                );
    
                CREATE INDEX building_geom_idx ON building USING gist (geom); -- 22 s
            ''', {'target_srid':GlobalSettings.get_target_srid()})
            db.commit()
            registry.register(db, schema, 'building', osm_source, osm_options, GlobalSettings.get_target_srid(), bbox, osm_coverage)
        h.logEndTask()

        # create dataset "crossing"
        h.logBeginTask('create dataset "crossing"')
        if registry.prepare_import(db, schema, 'crossing', ['crossing'], on_existing, osm_source, osm_options):
            db.execute('''
                CREATE TABLE crossing AS ( -- 4 s
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Point, %(target_srid)s) AS geom FROM osm_point WHERE highway IN ('crossing') UNION ALL
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(LineString, %(target_srid)s) AS geom FROM osm_line WHERE highway IN ('crossing') UNION ALL
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Polygon, %(target_srid)s) AS geom FROM osm_polygon WHERE highway IN ('crossing')
                );
    
                CREATE INDEX crossing_geom_idx ON crossing USING gist (geom); -- 1 s
            ''', {'target_srid':GlobalSettings.get_target_srid()})
            db.commit()
            registry.register(db, schema, 'crossing', osm_source, osm_options, GlobalSettings.get_target_srid(), bbox, osm_coverage)
        h.logEndTask()

        # create dataset "facility"
        h.logBeginTask('create dataset "facility"')
        if registry.prepare_import(db, schema, 'facility', ['facility'], on_existing, osm_source, osm_options):
            db.execute('''
                CREATE TABLE facility AS ( -- 3 s
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Point, %(target_srid)s) AS geom
                    FROM osm_point
                    WHERE amenity IN ('arts_centre', 'artwork', 'attraction', 'bar', 'biergarten', 'cafe', 'castle', 'cinema', 'community_centre', 'library', 'museum',
                                      'music_venue', 'park', 'pub', 'public_bookcase', 'restaurant', 'swimming_pool', 'theatre', 'toy_library', 'viewpoint', 'public_bath') -- entertainment
                       OR amenity IN ('atm', 'bureau_de_change', 'bakery', 'beverages', 'butcher', 'clothes', 'department_store', 'fast_food', 'marketplace',
                                      'florist', 'food_court', 'furniture_shop', 'ice_cream', 'kiosk', 'mall', 'outdoor_shop', 'pharmacy',
                                      'shoe_shop', 'sports_shop', 'internet_cafe', 'supermarket', 'commercial', 'retail', 'shop', 'bicycle_rental', 'boat_rental', 'car_rental', 'bank') -- retail
                       OR amenity IN ('university', 'school', 'college', 'gymnasium', 'kindergarten', 'childcare', 'boarding_school', 'music_school',
                                      'riding_school', 'driving_school', 'language_school', 'research_institute', 'school;dormitory', 'training', 'place_of_worship',
                                      'conference_centre', 'events_venue', 'exhibition_centre', 'social_centre', 'courthouse', 'post_office', 'ranger_station', 'townhall') -- institutional
                       OR amenity IN ('post_box', 'bbq', 'bench', 'drinking_water', 'give_box', 'shelter', 'toilets', 'water_point', 'watering_place', 
                                      'waste_basket', 'clock', 'kneipp_water_cure', 'lounger', 'vending_machine') -- infrastructure
                       OR tourism IN ('museum', 'attraction', 'gallery', 'viewpoint', 'zoo')
    
                    UNION ALL
    
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Polygon, %(target_srid)s) AS geom
                    FROM osm_polygon
                    WHERE amenity IN ('arts_centre', 'artwork', 'attraction', 'bar', 'biergarten', 'cafe', 'castle', 'cinema', 'community_centre', 'library', 'museum',
                                      'music_venue', 'park', 'pub', 'public_bookcase', 'restaurant', 'swimming_pool', 'theatre', 'toy_library', 'viewpoint', 'public_bath') -- entertainment
                       OR amenity IN ('atm', 'bureau_de_change', 'bakery', 'beverages', 'butcher', 'clothes', 'department_store', 'fast_food', 'marketplace', 'florist', 'food_court',
                                      'furniture_shop', 'ice_cream', 'kiosk', 'mall', 'outdoor_shop', 'pharmacy', 'shoe_shop', 'sports_shop', 'internet_cafe',
                                      'supermarket', 'commercial', 'retail', 'shop', 'bicycle_rental', 'boat_rental', 'car_rental', 'bank') -- retail
                       OR amenity IN ('university', 'school', 'college', 'gymnasium', 'kindergarten', 'childcare', 'boarding_school', 'music_school',
                                      'riding_school', 'driving_school', 'language_school', 'research_institute', 'school;dormitory', 'training', 'place_of_worship',
                                      'conference_centre', 'events_venue', 'exhibition_centre', 'social_centre', 'courthouse', 'post_office', 'ranger_station', 'townhall') -- institutional
                       OR amenity IN ('post_box', 'bbq', 'bench', 'drinking_water', 'give_box', 'shelter', 'toilets', 'water_point', 'watering_place', 
                                      'waste_basket', 'clock', 'kneipp_water_cure', 'lounger', 'vending_machine') -- infrastructure
                       OR tourism IN ('museum', 'attraction', 'gallery', 'viewpoint', 'zoo')
                );
    
                CREATE INDEX facility_geom_idx ON facility USING gist (geom); -- 1 s
            ''', {'target_srid':GlobalSettings.get_target_srid()})
            db.commit()
            registry.register(db, schema, 'facility', osm_source, osm_options, GlobalSettings.get_target_srid(), bbox, osm_coverage)
        h.logEndTask()

        # create dataset "greenness"
        h.logBeginTask('create dataset "greenness"')
        if registry.prepare_import(db, schema, 'greenness', ['greenness'], on_existing, osm_source, osm_options):
            db.execute('''
                CREATE TABLE greenness AS ( -- 14 s
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Polygon, %(target_srid)s) AS geom
                    FROM osm_polygon
                    WHERE landuse IN ('forest', 'grass', 'meadow', 'village_green', 'recreation_ground', 'vineyard', 'flowerbed', 'farmland', 'heath', 'nature_reserve', 'park', 'greenfield')
                       OR leisure IN ('garden', 'golf_course', 'park')
                       OR "natural" IN ('tree', 'wood', 'grassland', 'heath', 'scrub')
                );
    
                CREATE INDEX greenness_geom_idx ON greenness USING gist (geom); -- 4 s
            ''', {'target_srid':GlobalSettings.get_target_srid()})
            db.commit()
            registry.register(db, schema, 'greenness', osm_source, osm_options, GlobalSettings.get_target_srid(), bbox, osm_coverage)
        h.logEndTask()

        # create dataset "water"
        h.logBeginTask('create dataset "water"')
        if registry.prepare_import(db, schema, 'water', ['water'], on_existing, osm_source, osm_options):
            db.execute('''
                CREATE TABLE water AS ( -- 10 s
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(LineString, %(target_srid)s) AS geom FROM osm_line WHERE (waterway IS NOT NULL OR "natural" = 'water') AND tunnel IS NULL UNION ALL
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Polygon, %(target_srid)s) AS geom FROM osm_polygon WHERE (waterway IS NOT NULL OR "natural" = 'water') AND tunnel IS NULL
                );
    
                CREATE INDEX water_geom_idx ON water USING gist (geom); -- 1 s
            ''', {'target_srid':GlobalSettings.get_target_srid()})
            db.commit()
            registry.register(db, schema, 'water', osm_source, osm_options, GlobalSettings.get_target_srid(), bbox, osm_coverage)
        h.logEndTask()

        # create dataset "parking"
        h.logBeginTask('create dataset "parking"')
        if registry.prepare_import(db, schema, 'parking', ['parking'], on_existing, osm_source, osm_options):
            db.execute('''
            CREATE TABLE parking AS (
            WITH road AS (
                SELECT way, highway, service,
                       -- most specific motor vehicle access tag decides
                       COALESCE(motorcar, tags -> 'motor_vehicle', tags -> 'vehicle', access) AS motor_access,
                       -- parking per side: side-specific key first, then both sides
                       COALESCE(tags -> 'parking:left', tags -> 'parking:both', tags -> 'parking',
                                tags -> 'parking:lane:left', tags -> 'parking:lane:both', tags -> 'parking:lane') AS parking_left,
                       COALESCE(tags -> 'parking:right', tags -> 'parking:both', tags -> 'parking',
                                tags -> 'parking:lane:right', tags -> 'parking:lane:both', tags -> 'parking:lane') AS parking_right
                FROM osm_line
                WHERE osm_id > -1 -- filter to exclude routes
                      AND highway IS NOT NULL
            )
            SELECT ST_Transform(way, %(target_srid)s)::geometry(LineString, %(target_srid)s) AS geom,
                   CASE
                       -- parking present on at least one side
                       WHEN parking_left = ANY ('{lane,street_side,on_kerb,half_on_kerb,shoulder,layby,surface,separate,yes,parallel,diagonal,perpendicular,marked,both,left,right}') OR
                            parking_right = ANY ('{lane,street_side,on_kerb,half_on_kerb,shoulder,layby,surface,separate,yes,parallel,diagonal,perpendicular,marked,both,left,right}') OR
                            service = 'parking_aisle'
                           THEN 'allowed'
                       -- no parking on both sides
                       WHEN parking_left = ANY ('{no,no_parking,no_stopping,fire_lane}') AND
                            parking_right = ANY ('{no,no_parking,no_stopping,fire_lane}')
                           THEN 'forbidden'
                       -- roads with unrestricted motor vehicle access: cars are permitted but parking is not specified
                       WHEN highway = ANY ('{primary,primary_link,secondary,secondary_link,tertiary,tertiary_link,unclassified,residential,service,road}') AND
                            (motor_access IS NULL OR motor_access = ANY ('{yes,designated,permissive,destination,customers}')) AND
                            (service IS NULL OR service != ALL ('{driveway,drive-through,emergency_access}'))
                           THEN 'implicit'
                       -- all other ways: no motorized traffic, restricted motor vehicle access (e.g. private, agricultural, forestry),
                       -- parking legally prohibited (motorway, trunk), parking only in marked spots (living_street),
                       -- or service roads without parking along them (driveway, drive-through, emergency_access)
                       ELSE 'forbidden'
                   END AS parking
            FROM road
            UNION ALL
            SELECT ST_Transform(way, %(target_srid)s)::geometry(Polygon, %(target_srid)s) AS geom,
                        'allowed' AS parking -- dedicated parking
            FROM osm_polygon
             WHERE amenity LIKE 'parking' AND (
				(tags -> 'parking' IS NULL OR tags -> 'parking' != 'underground') AND
				(tags -> 'level' IS NULL OR tags -> 'level' != '-1') AND
				(tags -> 'parking' IS NULL OR tags -> 'parking' != 'multi-storey')
			));
                CREATE INDEX parking_geom_idx ON parking USING gist (geom); -- 1 s
            ''', {'target_srid': GlobalSettings.get_target_srid()})
            db.commit()
            registry.register(db, schema, 'parking', osm_source, osm_options, GlobalSettings.get_target_srid(), bbox, osm_coverage)
        h.logEndTask()
        
        # create dataset "sights"
        h.logBeginTask('create dataset "sights"')
        if registry.prepare_import(db, schema, 'sights', ['sights'], on_existing, osm_source, osm_options):
            db.execute('''
                CREATE TABLE sights AS (
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Point, %(target_srid)s) AS geom, name, historic, tourism
                    FROM osm_point
                    WHERE historic <> 'no'
                       OR tourism IN ('attraction', 'museum', 'artwork', 'viewpoint', 'picnic_site', 'zoo', 'theme_park', 'gallery')
                );

                CREATE INDEX sights_geom_idx ON sights USING gist (geom); -- 1 s
            ''', {'target_srid': GlobalSettings.get_target_srid()})
            db.commit()
            registry.register(db, schema, 'sights', osm_source, osm_options, GlobalSettings.get_target_srid(), bbox, osm_coverage)
        h.logEndTask()

        # close database connection
        h.debugLog('close database connection')
        db.close()


def create_importer(db_settings: DbSettings, import_type: str):
    if import_type.lower() == InputType.GIP.value.lower():
        return GipImporter(db_settings)
    if import_type.lower() == InputType.GIP2.value.lower():
        return Gip2Importer(db_settings)
    if import_type.lower() == InputType.OSM.value.lower():
        return OsmImporter(db_settings)
    raise NotImplementedError(f"import type '{import_type}' not implemented")
