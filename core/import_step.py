import os
import re
import subprocess
from urllib.error import HTTPError
import urllib.request
import zipfile
from osgeo import ogr
from typing import List

import toolbox.helper as h
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings, InputType
from toolbox.dbhelper import PostgresConnection


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


def import_geopackage(connection_string: str, path: str, schema: str, table: str, fid: str = None, target_srid: int = None, layers: List[str] = None,  attributes: List[str] = None, geometry_types: List[str] = None) -> None:  # TODO: @CW: add error handling
    """Takes in a path to a geopackage file and imports it to a database table."""
    data_source = ogr.Open(path)

    attributes = [] if attributes is None else attributes
    attributes = ','.join(attribute for attribute in attributes)

    geometry_types = [] if geometry_types is None else geometry_types
    geometry_types = ', '.join(f"'{geometry_type}'" for geometry_type in geometry_types)

    layers = [layer.GetName() for layer in data_source] if layers is None else layers
    layers_geometry_types = set(data_source.GetLayerByName(layer).GetGeomType() for layer in layers)

    fid = f"-lco FID={fid}" if fid else "-lco FID=fid"
    transform = f"-t_srs EPSG:{target_srid}" if target_srid else ""
    geometry_type = "-nlt GEOMETRY" if len(layers_geometry_types) > 1 else ""

    for layer in layers:
        h.log(f"import layer \"{layer}\"")
        geometry_column = data_source.GetLayerByName(layer).GetGeometryColumn()

        select = f"-select \"{attributes}\"" if attributes else ""
        where = f"-where \"ST_GeometryType({geometry_column}) IN ({geometry_types})\"" if geometry_types else ""
        
        result = subprocess.run(f"ogr2ogr -f PostgreSQL \"PG:{connection_string}\" {fid} -skipfailures -lco GEOMETRY_NAME=geom -nln {schema}.{table} {transform} {geometry_type} {select} {where} \"{path}\" \"{layer}\"", 
            shell=True, check=True)
        h.debugLog(f"ogr2ogr returned code: {result.returncode}")
        #h.debugLog(f"ogr2ogr stdout: {result.args}")


def import_osm(connection_string: str, path: str, path_style: str, schema: str, prefix: str = None) -> None:
    """Takes in a path to an osm pbf file and imports it to database tables."""
    prefix = f"--prefix {prefix}" if prefix else ""

    subprocess.run(f"osm2pgsql --database={connection_string} --middle-schema={schema} --output-pgsql-schema={schema} {prefix} --latlong --slim --hstore --style=\"{path_style}\" \"{path}\"", 
        shell=True, check=True)


class GipImporter(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict):
        h.info('importing gip')
        h.log(f"using import settings: {str(settings)}")

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
        h.log('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.init_extensions_and_schema(schema)

        # extract zip files
        h.logBeginTask('extract zip files')
        with zipfile.ZipFile(os.path.join(directory, settings['filename_A']), 'r') as zf:
            for file in files_A:
                if not os.path.isfile(os.path.join(directory, os.path.splitext(settings['filename_A'])[0], file['filename'])):
                    zf.extract(file['filename'], os.path.join(directory, os.path.splitext(settings['filename_A'])[0]))
        h.logEndTask()

        # create tables from files_A
        for file in files_A:
            h.logBeginTask(f"create table \"{file['table']}\"")
            if not os.path.isfile(os.path.join(directory, os.path.splitext(settings['filename_A'])[0], f"{os.path.splitext(file['filename'])[0]}.csv")):
                create_csv(os.path.join(directory, os.path.splitext(settings['filename_A'])[0], file['filename']))
            if not os.path.isfile(os.path.join(directory, os.path.splitext(settings['filename_A'])[0], f"{os.path.splitext(file['filename'])[0]}.sql")):
                create_sql(os.path.join(directory, os.path.splitext(settings['filename_A'])[0], file['filename']))

            db.drop_table(file['table'], schema=schema)
            db.execute_sql_from_file(f"{os.path.splitext(file['filename'])[0]}", os.path.join(directory, os.path.splitext(settings['filename_A'])[0]))
            db.commit()

            import_csv(db.connection_string, os.path.join(directory, os.path.splitext(settings['filename_A'])[0], f"{os.path.splitext(file['filename'])[0]}.csv"), schema, table=file['table'])

            db.add_primary_key(file['table'], file['columns'], schema=schema)
            db.commit()
            h.logEndTask()

        # close database connection
        h.log('closing database connection')
        db.close()


class OsmImporter(DbStep):
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

    def _load_osm_from_placename(self, db: PostgresConnection, data_schema: str, data_directory: str, settings: dict):
        # local imports, as we only use these here (makes it optional dependency for stand-alone use)    
        import requests as rq
        import osm2geojson as o2g
        # prepare DB: create schema and setup extensions
        db.create_schema(data_schema)
        # first, set target schema
        db.schema = data_schema
        aoi_table = self.db_settings.entities.table_aoi
        aoi_name = GlobalSettings.case_id
        on_existing = settings['on_existing']
        # create AOI table if it not already exists
        db.ex(f"""CREATE TABLE IF NOT EXISTS {aoi_table} (
            id    serial NOT NULL PRIMARY KEY,
            name  varchar(40) NOT NULL CHECK (name <> '') UNIQUE,
            geom  geometry,
            srid  integer
        );""")

        # check whether an AOI with the given name already exists
        excnt = db.query_one("SELECT COUNT(*) FROM " + aoi_table + " WHERE name = %s;", (aoi_name,))[0]
        if excnt > 0:
            h.info(f"found {excnt} entry in existing AOI table with the given AOI name '{aoi_name}'")
            # if exists, use param switch or ask whether to use an existing AOI or overwrite it
            if  on_existing == 'delete':
                h.info("...you specified to overwrite the existing AOI entry.")
                # delete existing AOI from AOI table
                db.ex("DELETE FROM " + data_schema + "." + aoi_table + " WHERE name = %s;", (aoi_name,))
                # continue script execution
            elif on_existing == 'skip':
                h.info("...you chose to re-use the existing AOI entry. Skipping AOI download.")
                return
            else:
                raise Exception("An AOI with the given id already exists. Please resolve the conflict manually or provide a different option for the import setting 'on_exists': [skip/delete/abort]")
        else:
            h.info("AOI name '" + aoi_name + "' is not in use -> continuing with AOI download...")
        
        # download AOI
        # first: create AOI query string
        h.debugLog(f"preparing AOI query for {settings['place_name']}")
        o_add_filter = ""
        if h.has_keys(settings, ['admin_level']):
            o_add_filter += "[admin_level='" + str(settings['admin_level']) + "']" 
        if h.has_keys(settings, ['zip_code']):
            o_add_filter += "[\"admin_centre:postal_code\"='" + str(settings['zip_code']) + "']"
        overpass_aoi_api_string = f"""
            area
            [name='{settings['place_name']}'][boundary='administrative']{o_add_filter};
            rel(pivot);
            out body;
            >;
            out skel qt;
        """
        h.debugLog(f"AOI query string: {overpass_aoi_api_string}")
        # download AOI geom and add to aoi table
        h.logBeginTask("Downloading AOI...")
        curEndpointIndex = 0
        success = False
        while curEndpointIndex < len(GlobalSettings.overpass_api_endpoints) and not success:
            try:
                aoi_response = rq.get(GlobalSettings.overpass_api_endpoints[curEndpointIndex], params={'data': overpass_aoi_api_string}, timeout=5)
                aoi_response.raise_for_status()
            except HTTPError as e:
                h.log(f"HTTPError while trying to download OSM AOI from '{GlobalSettings.overpass_api_endpoints[curEndpointIndex]}': Error code {e.code}\n{e.args}\n{e.info()} --> trying again with next available API endpoint...")
                curEndpointIndex+=1
            except KeyboardInterrupt:
                h.majorInfo(f"OSM AOI download from '{GlobalSettings.overpass_api_endpoints[curEndpointIndex]}' interrupted by user. Terminating.")
                exit()
            except BaseException as e:
                h.majorInfo(f"An unexpected ERROR occured during OSM AOI download from '{GlobalSettings.overpass_api_endpoints[curEndpointIndex]}': {e.args}")
                curEndpointIndex+=1
            else:
                success = True
                h.log(f"Response headers from API call to {GlobalSettings.overpass_api_endpoints[curEndpointIndex]}: {aoi_response.headers}", h.LOG_LEVEL_4_DEBUG)
                h.log(f"OSM AOI Download from {GlobalSettings.overpass_api_endpoints[curEndpointIndex]} succeeded.")
        if not success:
            raise Exception("OSM data download was not successful. Terminating.")
        h.logEndTask()

        aoi_geoJson = o2g.xml2geojson(aoi_response.text)
        num_ft = len(aoi_geoJson['features'])
        if num_ft < 1:
            h.majorInfo("ERROR: no matching feature found. Please try again with different AOI query settings.")
            raise Exception("AOI not found. Please check your query settings or use a bounding box instead (parameter 'bbox' in 'import' section of settings file).")
        # by default, use the first result (in case there were more results returned)
        fid = 0 
        if num_ft > 1:
            h.info(f"Found {num_ft} matching features:")
            i = 0
            for ft in aoi_geoJson['features']:
                i+=1
                if "tags" in ft["properties"]:
                    print("->", str(i), "--- Type:", ft["type"], "ZIP-Code:", ft["properties"]["tags"]["admin_centre:postal_code"] if "admin_centre:postal_code" in ft["properties"]["tags"] else "-", 
                        "Admin level:", ft["properties"]["tags"]["admin_level"] if "admin_level" in ft["properties"]["tags"] else "-", "Wikipedia:", ft["properties"]["tags"]["wikipedia"] if "wikipedia" in ft["properties"]["tags"] else "-")
                else:
                    print("->", str(i), "--- Type:", ft["type"])
            if h.has_keys(settings, ['interactive']) and settings['interactive']:
                # let user choose which result to use if more than one AOI was found
                fid = int(input("Which one do you want to use? [1.." + str(i) + "] for your choice, other number to abort:\t"))
                if not fid in range(i+1) or fid < 1:
                    print("You chose to abort the process. Will now exit.")
                    exit("User cancelled processing during AOI choice")
                print("You chose to continue with AOI #", fid)
                fid -= 1 # back to 0-based index value
            else:
                print("Using the first search result. If you want to use a different AOI, either provide more query parameters or add 'interactive: True' to the import settings for an interactive choice.")
        
        h.logBeginTask("importing AOI to db table...")
        aoi_geoJson = aoi_geoJson['features'][fid]
        h.debugLog("geoJson: " + str(aoi_geoJson))
        db.ex("INSERT INTO " + aoi_table + " (name, geom) VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s::text),4326));", (aoi_name, str(aoi_geoJson["geometry"])))
        db.commit()
        h.logEndTask()

        # now, data download can be prepared
        # determine SRID if not specified manually
        srid = GlobalSettings.custom_srid
        if srid is None:
            srid = self._get_srid_for_AOI(db, aoi_name, aoi_table, data_schema)
            GlobalSettings.default_srid = srid
        else:
            # save cusom SRID to AOI table
            self._save_srid_for_AOI(srid, db, aoi_name, aoi_table, data_schema)

        # get BBox for network coverage (larger than chosen AOI -> prevent edge effects)
        buffer = 500
        if h.has_keys(settings, ['buffer']):
            buffer = settings['buffer']
        bbox = db.query_one("WITH a as (SELECT ST_Transform(ST_setSRID(ST_EXPAND(box2d(ST_Transform(geom, %s)),%s),%s), 4326) as bbox FROM " + 
                                    aoi_table + """ WHERE name=%s) 
                                    SELECT ST_YMIN(bbox), ST_XMIN(bbox), ST_YMAX(bbox), ST_XMAX(bbox) FROM a;""", 
                                    (srid, buffer, srid, aoi_name,)
                                )
        h.debugLog(f"Determined Bounding box: {bbox}")
        # load OSM data from bounding box
        self._load_osm_from_bbox(str(bbox)[1:-1], settings)

    def _load_osm_from_bbox(self, bbox: str, settings: dict):
        q_template: str = """
            [timeout:900][maxsize:1073741824];
            nwr[!"boundary"][!"place"][!power]["route"!="bus"]["route"!="road"]["route"!="ferry"]["route"!="power"]["route"!="train"]["route"!="railway"](__bbox__);
            (._;>;);
            out;"""
        net_file = f"{GlobalSettings.osm_download_prefix}_{GlobalSettings.case_id}.xml"
        if os.path.isfile(os.path.join(GlobalSettings.data_directory, net_file)):
            if not h.has_keys(settings, ['on_existing']):
                raise Exception("Target file for OSM download already exists. Please add a value for 'on_existing' to the import settings. [skip/abort/delete]")
            if settings['on_existing'] == 'skip':
                h.info("Target file for OSM download already exists. Skipping download (re-using existing file). You can change this behavior by adding a value for 'on_existing' to the import settings. [skip/abort/delete]")
                return
            if settings['on_existing'] != 'delete':
                raise Exception("Target file for OSM download already exists. Aborting. Please resolve the conflict manually or specify a different value for 'on_existing' in the import settings. [skip/abort/delete]")     
            else:
                h.info("Target file for OSM download already exists. Deleting existing file and proceeding with download. You can change this behavior by adding a value for 'on_existing' to the import settings. [skip/abort/delete]")
        q_str = q_template.replace("__bbox__", bbox)
        h.debugLog(f"prepared OSM overpass API query: \n'{q_str}")

        h.logBeginTask("Starting OSM data download...")
        curEndpointIndex = 0
        success = False
        while curEndpointIndex < len(GlobalSettings.overpass_api_endpoints) and not success:
            success = False
            try:
                file_name, headers = urllib.request.urlretrieve(
                    GlobalSettings.overpass_api_endpoints[curEndpointIndex] + "?data=" + urllib.parse.quote_plus(q_str), 
                    os.path.join(GlobalSettings.data_directory, net_file))
            except HTTPError as e:
                h.log(f"HTTPError while trying to download OSM data from '{GlobalSettings.overpass_api_endpoints[curEndpointIndex]}': Error code {e.code}\n{e.args}\n{e.info()} --> trying again with next available API endpoint...")
                curEndpointIndex+=1
            except KeyboardInterrupt:
                h.majorInfo(f"OSM download from '{GlobalSettings.overpass_api_endpoints[curEndpointIndex]}' interrupted by user. Terminating.")
                exit()
            except BaseException as e:
                h.log(f"An unexpected ERROR occured during OSM data download from '{GlobalSettings.overpass_api_endpoints[curEndpointIndex]}': {e.args}")
                curEndpointIndex+=1
            else:
                success = True
                h.log(f"Response headers from API call to {GlobalSettings.overpass_api_endpoints[curEndpointIndex]}: {headers}", h.LOG_LEVEL_4_DEBUG)
                h.log(f"OSM Download from {GlobalSettings.overpass_api_endpoints[curEndpointIndex]} succeeded.")
        if not success:
            raise Exception("OSM data download was not successful. Terminating.")
        h.logEndTask()

    def run_step(self, settings: dict):
        h.info('importing osm')
        h.log(f"using settings: {str(settings)}")
        use_overpass_api: bool = False

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)

        # if needed, download OSM data
        if not h.has_keys(settings, ['filename']):
            h.info("no OSM file provided. Checking for Overpass API settings instead...")
            if not h.has_any_key(settings, ['place_name', 'bbox']):
                raise Exception("neither 'aoi_name' nor 'bbox' parameter specified for OSM download. Terminating.")
            use_overpass_api = True
            # start OSM import through overpass API
            # import from bounding box
            if h.has_keys(settings, ['bbox']):
                self._load_osm_from_bbox(settings['bbox'], settings)
            # import from place name
            elif h.has_keys(settings, ['place_name']):
                self._load_osm_from_placename(db, schema, directory, settings)

        # import osm file
        h.logBeginTask('import osm file')
        db.drop_table("osm_point", schema=schema)
        db.drop_table("osm_line", schema=schema)
        db.drop_table("osm_polygon", schema=schema)
        db.drop_table("osm_nodes", schema=schema)
        db.drop_table("osm_rels", schema=schema)
        db.drop_table("osm_roads", schema=schema)
        db.drop_table("osm_ways", schema=schema)
        db.commit()

        filename = f"{GlobalSettings.osm_download_prefix}_{GlobalSettings.case_id}.xml"
        if not use_overpass_api:
            filename = settings['filename']
        import_osm(db.connection_string, os.path.join(directory, filename), os.path.join('resources', 'default.style'), schema, prefix='osm')  # 12 m 35 s

        db.drop_table("osm_nodes", schema=schema)
        db.drop_table("osm_rels", schema=schema)
        db.drop_table("osm_roads", schema=schema)
        db.drop_table("osm_ways", schema=schema)
        db.commit()
        h.logEndTask()

        # create dataset "building"
        h.logBeginTask('create dataset "building"')
        if db.handle_conflicting_output_tables(['building'], schema):
            db.execute('''
                CREATE TABLE building AS ( -- 16 s
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Polygon, %(target_srid)s) AS geom
                    FROM osm_polygon
                    WHERE building IS NOT NULL
                );
    
                CREATE INDEX building_geom_idx ON building USING gist (geom); -- 22 s
            ''', {'target_srid':GlobalSettings.get_target_srid()})
            db.commit()
        h.logEndTask()

        # create dataset "crossing"
        h.logBeginTask('create dataset "crossing"')
        if db.handle_conflicting_output_tables(['crossing'], schema):
            db.execute('''
                CREATE TABLE crossing AS ( -- 4 s
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Point, %(target_srid)s) AS geom FROM osm_point WHERE highway IN ('crossing') UNION ALL
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(LineString, %(target_srid)s) AS geom FROM osm_line WHERE highway IN ('crossing') UNION ALL
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Polygon, %(target_srid)s) AS geom FROM osm_polygon WHERE highway IN ('crossing')
                );
    
                CREATE INDEX crossing_geom_idx ON crossing USING gist (geom); -- 1 s
            ''', {'target_srid':GlobalSettings.get_target_srid()})
            db.commit()
        h.logEndTask()

        # create dataset "facility"
        h.logBeginTask('create dataset "facility"')
        if db.handle_conflicting_output_tables(['facility'], schema):
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
                                      'furniture_shop', 'ice_cream', 'kiosk', 'mall', 'outdoor_shop', 'pharmacy', 'shoe_shop', 'sports_shop', 'internet_cafe'
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
        h.logEndTask()

        # create dataset "greenness"
        h.logBeginTask('create dataset "greenness"')
        if db.handle_conflicting_output_tables(['greenness'], schema):
            db.execute('''
                CREATE TABLE greenness AS ( -- 14 s
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Polygon, %(target_srid)s) AS geom
                    FROM osm_polygon
                    WHERE landuse IN ('forest', 'grass', 'meadow', 'village_green', 'recreation_ground', 'vineyard', 'flowerbed', 'farmland', 'heath', 'nature_reseve', 'park', 'greenfield')
                       OR leisure IN ('garden', 'golf_course', 'park')
                       OR "natural" IN ('tree', 'wood', 'grassland', 'heath', 'scrub')
                );
    
                CREATE INDEX greenness_geom_idx ON greenness USING gist (geom); -- 4 s
            ''', {'target_srid':GlobalSettings.get_target_srid()})
            db.commit()
        h.logEndTask()

        # create dataset "water"
        h.logBeginTask('create dataset "water"')
        if db.handle_conflicting_output_tables(['water'], schema):
            db.execute('''
                CREATE TABLE water AS ( -- 10 s
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(LineString, %(target_srid)s) AS geom FROM osm_line WHERE (waterway IS NOT NULL OR "natural" = 'water') AND tunnel IS NULL UNION ALL
                    SELECT ST_Transform(way, %(target_srid)s)::geometry(Polygon, %(target_srid)s) AS geom FROM osm_polygon WHERE (waterway IS NOT NULL OR "natural" = 'water') AND tunnel IS NULL
                );
    
                CREATE INDEX water_geom_idx ON water USING gist (geom); -- 1 s
            ''', {'target_srid':GlobalSettings.get_target_srid()})
            db.commit()
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()


def create_importer(db_settings: DbSettings, import_type: str):
    if import_type.lower() == InputType.GIP.value.lower():
        return GipImporter(db_settings)
    if import_type.lower() == InputType.OSM.value.lower():
        return OsmImporter(db_settings)
    raise NotImplementedError(f"import type '{import_type}' not implemented")
