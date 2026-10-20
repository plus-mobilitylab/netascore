import toolbox.helper as h
from core import dataset_registry as registry
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings, InputType
from toolbox.dbhelper import PostgresConnection


class GipNetworkStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict):
        h.debugLog('network step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.debugLog('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.init_extensions_and_schema(schema)

        # execute "gip_network"
        h.logBeginTask('execute "gip_network"')
        if db.handle_conflicting_output_tables(['network_edge', 'network_node']):
            regional_code = settings.get('regional_code') if settings else None
            bbox = h.parse_bbox(settings['bbox']) if h.has_keys(settings, ['bbox']) and settings['bbox'] else None
            params = {
                'schema_network': schema,
                'schema_data': self.db_settings.entities.data_schema,
                'target_srid': GlobalSettings.get_target_srid(),
                'regional_codes': [] if not regional_code else regional_code if isinstance(regional_code, list) else [regional_code],
                'bbox': bbox or [],
                'bbox_ymin': None if not bbox else bbox[0],
                'bbox_xmin': None if not bbox else bbox[1],
                'bbox_ymax': None if not bbox else bbox[2],
                'bbox_xmax': None if not bbox else bbox[3]
            }
            db.execute_template_sql_from_file("gip_network", params)
            db.commit()
        h.logEndTask()

        # close database connection
        h.debugLog('closing database connection')
        db.close()


class Gip2NetworkStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict):
        h.debugLog('network step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.debugLog('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.init_extensions_and_schema(schema)
        db.verify_input_tables_exist(
            ['gip2_node', 'gip2_link', 'gip2_linkcoordinate', 'gip2_linear_use_part', 'gip2_bikehike'],
            schema=self.db_settings.entities.data_schema
        )

        # execute "gip2_network"
        h.logBeginTask('execute "gip2_network"')
        if db.handle_conflicting_output_tables(['network_edge', 'network_node']):
            regional_code = settings.get('regional_code') if settings else None
            bbox = h.parse_bbox(settings['bbox']) if h.has_keys(settings, ['bbox']) and settings['bbox'] else None
            params = {
                'schema_network': schema,
                'schema_data': self.db_settings.entities.data_schema,
                'target_srid': GlobalSettings.get_target_srid(),
                'regional_codes': [] if not regional_code else regional_code if isinstance(regional_code, list) else [regional_code],
                'bbox': bbox or [],
                'bbox_ymin': None if not bbox else bbox[0],
                'bbox_xmin': None if not bbox else bbox[1],
                'bbox_ymax': None if not bbox else bbox[2],
                'bbox_xmax': None if not bbox else bbox[3]
            }
            db.execute_template_sql_from_file("gip2_network", params)
            db.commit()
        h.logEndTask()

        # close database connection
        h.debugLog('closing database connection')
        db.close()


class OsmNetworkStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict):
        h.debugLog('network step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.debugLog('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.init_extensions_and_schema(schema)

        # create functions
        h.log('create functions')
        db.execute_sql_from_file("osm_delete_dangling_edges", "sql/functions")
        db.commit()

        # the OSM tables in the shared data schema are replaced by every OSM import - make sure they match the current case
        # will throw an exception in case of mismatch
        registry.check_osm_import(db, self.db_settings.entities.data_schema)

        # determine clipping of the network to the area of interest (requires an AOI entry, e.g. from OSM download)
        clip_mode = h.get_clip_mode(settings)
        if clip_mode != 'none':
            data_schema = self.db_settings.entities.data_schema
            aoi_table = self.db_settings.entities.table_aoi
            has_aoi_table = db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (f"{data_schema}.{aoi_table}",))[0]
            has_aoi = has_aoi_table and db.query_one(f"SELECT COUNT(*) FROM {data_schema}.{aoi_table} WHERE name = %s AND geom IS NOT NULL;",
                                                     (GlobalSettings.case_id,))[0] > 0
            if not has_aoi:
                h.info(f"No AOI found for case '{GlobalSettings.case_id}' - network is not clipped. Specify 'bbox', 'place_name', or 'aoi_filename' in the import settings to enable clipping.")
                clip_mode = 'none'
            else:
                h.info(f"clipping network to the area of interest (clip mode: '{clip_mode}')")
        buffer = 0
        if settings and h.has_keys(settings, ['buffer']):
            buffer = settings['buffer']

        # execute "osm_network"
        h.logBeginTask('execute "osm_network"')
        if db.handle_conflicting_output_tables(['network_edge', 'network_node', 'network_bicycle_route']):
            params = {
                'schema_network': schema,
                'schema_data': self.db_settings.entities.data_schema,
                'target_srid': GlobalSettings.get_target_srid(),
                'include_rail': settings and h.has_keys(settings, ['include_rail']) and settings['include_rail'],
                'include_aerialway': settings and h.has_keys(settings, ['include_aerialway']) and settings['include_aerialway'],
                'clip_mode': None if clip_mode == 'none' else clip_mode,
                'clip_buffer': buffer,
                'table_aoi': self.db_settings.entities.table_aoi,
                'aoi_name': GlobalSettings.case_id
            }
            db.execute_template_sql_from_file("osm_network", params)
            db.commit()
        h.logEndTask()

        # close database connection
        h.debugLog('closing database connection')
        db.close()


def create_network_step(db_settings: DbSettings, import_type: str):
    if import_type.lower() == InputType.GIP.value.lower():
        return GipNetworkStep(db_settings)
    if import_type.lower() == InputType.GIP2.value.lower():
        return Gip2NetworkStep(db_settings)
    if import_type.lower() == InputType.OSM.value.lower():
        return OsmNetworkStep(db_settings)
    raise NotImplementedError(f"import type '{import_type}' not implemented")
