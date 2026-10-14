import re
import sys

import toolbox.helper as h
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings, InputType
from toolbox.dbhelper import PostgresConnection


# default input data attributes which will be added to the export in case of "include_source_attributes: True" in export settings
OSM_DEFAULT_SOURCE_ATTRIBUTES = ['name', 'highway', 'ref', 'maxspeed', 'surface', 'smoothness', 'tracktype', 'width', 'lit',
                                 'oneway', 'junction', 'access', 'motor_vehicle', 'foot', 'bicycle', 'sidewalk', 'cycleway', 'segregated', 'service']
GIP_DEFAULT_SOURCE_ATTRIBUTES = [
    'name1', 'name2', 'speed_tow_car', 'speed_bkw_car', 'speed_tow_truck', 'speed_bkw_truck', 'maxspeed_tow_car', 'maxspeed_bkw_car',
    'maxspeed_tow_truck', 'maxspeed_bkw_truck', 'access_tow', 'access_bkw', 'funcroadclass', 'cap_tow', 'cap_bkw', 'lanes_tow', 'lanes_bkw',
    'formofway', 'brunnel', 'maxheight', 'maxwidth', 'maxpressure', 'abutter_car', 'abutter_lorry', 'u_turn', 'slope', 'urban', 'level',
    'baustatus', 'toll', 'subnet_id', 'oneway', 'blt', 'blb', 'streetcat', 'agg_typ', 'sustainer', 'regcode', 'dbcon',
    'lu_use_id', 'lu_count', 'lu_offset', 'lu_width', 'lu_minwidth', 'lu_from_percent', 'lu_to_percent', 'lu_basetype',
    'lu_use_access_tow', 'lu_use_access_bkw', 'lu_surface', 'lu_electric',
    'bh_use_access_tow', 'bh_use_access_bkw', 'bh_bikeenvironment', 'bh_bikequalitytow', 'bh_bikequalitybkw', 'bh_bikedirecttow',
    'bh_bikedirectbkw', 'bh_bikesignedtow', 'bh_bikesignedbkw', 'bh_bikerecommtow', 'bh_bikerecommbkw', 'bh_bikewithfoottow',
    'bh_bikewithfootbkw', 'bh_bikefeaturetow', 'bh_bikefeaturebkw', 'bh_walkfeaturetow', 'bh_walkfeaturebkw']
GIP2_DEFAULT_SOURCE_ATTRIBUTES = [
    'name_text_hr', 'short_name_hr', 'name_text_additional', 'speed_tow_car', 'speed_bkw_car', 'maxspeed_tow_car', 'maxspeed_bkw_car',
    'access_tow', 'access_bkw', 'functional_class', 'lanes_tow_max', 'lanes_bkw_max', 'lanes_tow_min', 'lanes_bkw_min', 'form_of_way',
    'abutter_car', 'urban', 'level_intermediate', 'construction_state', 'toll', 'subnet', 'oneway_car', 'edge_category', 'sustainer',
    'regional_code', 'connector', 'owner', 'oneway_pedestrian', 'oneway_bike', 'oneway_bus',
    'lup_short_id', 'lup_link_percentage_from', 'lup_link_percentage_to', 'lup_offset_average', 'lup_width_average', 'lup_width_minimal',
    'lup_base_type', 'lup_access_tow', 'lup_access_bkw', 'lup_surface', 'lup_electric',
    'lup_oneway_pedestrian', 'lup_oneway_bike', 'lup_oneway_car', 'lup_oneway_bus',
    'bh_access_tow', 'bh_access_bkw', 'bh_surface', 'bh_bike_difficulty_tow', 'bh_bike_difficulty_bkw',
    'bh_bike_signed_tow', 'bh_bike_signed_bkw', 'bh_bike_recommendation_tow', 'bh_bike_recommendation_bkw',
    'bh_bike_feature_tow', 'bh_bike_feature_bkw', 'bh_walk_feature_tow', 'bh_walk_feature_bkw', 'bh_oneway_pedestrian', 'bh_oneway_bike']


def build_source_attributes_sql(db: PostgresConnection, schema: str, export_settings: dict, default_columns: list, prefix: str) -> str:
    """Compiles the SQL column list for source attributes to be added to the export (export setting "include_source_attributes").
    -> either boolean (True: predefined set of columns) or a list of column names.
    Columns are exported with the given prefix ("osm_" or "gip_") to distinguish them from NetAScore columns."""
    setting = export_settings.get('include_source_attributes') if isinstance(export_settings, dict) else None
    if setting is None or setting is False:
        return ""
    if setting is True:
        names = list(default_columns)
    elif isinstance(setting, list) and all(isinstance(v, str) and v.strip() for v in setting):
        names = [v.strip() for v in setting]
    else:
        h.majorInfo(f"error: export setting 'include_source_attributes' needs to be True/False or a list of column names. Found: {setting}")
        sys.exit(1)
    is_osm = prefix == "osm_"
    # available source columns
    rows = db.query_all("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = 'network_edge';", (schema,))
    columns = {r[0] for r in rows} - {'geom', 'tags'}
    parts = []
    out_names = {'osm_id', 'gip_id'}  # id columns of the export
    for name in names:
        if name in columns:
            expr = f'"{name}"'
        elif is_osm and name.replace(':', '_') in columns:
            expr = f'"{name.replace(":", "_")}"'  # OSM keys with own column are renamed in the network (e.g. addr:housenumber)
        elif is_osm and re.fullmatch(r"[A-Za-z0-9_:.\-]+", name):
            expr = f"tags -> '{name}'"  # OSM tag key
        elif is_osm:
            h.majorInfo(f"error: invalid OSM tag key '{name}' in export setting 'include_source_attributes'.")
            sys.exit(1)
        else:
            h.majorInfo(f"error: column '{name}' in export setting 'include_source_attributes' does not exist in the network. "
                        f"Available columns: {', '.join(sorted(columns))}")
            sys.exit(1)
        out = prefix + re.sub(r"[^A-Za-z0-9_]", "_", name)
        if out in out_names:
            h.info(f"source attribute '{name}' is listed more than once or conflicts with an id column - skipping.")
            continue
        out_names.add(out)
        parts.append(f'{expr} AS "{out}"')
    h.info(f"adding {len(parts)} source attributes to the export")
    return "".join(f", {p}" for p in parts)


class GipAttributesStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict, export_settings: dict = None):
        h.info('attributes step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.log('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.schema = schema

        # create functions
        h.log('create functions')
        db.execute_sql_from_file("gip_calculate_bicycle_infrastructure", "sql/functions")
        db.execute_sql_from_file("gip_calculate_pedestrian_infrastructure", "sql/functions")
        db.execute_sql_from_file("gip_calculate_road_category", "sql/functions")
        db.commit()

        # execute "gip_attributes"
        h.logBeginTask('execute "gip_attributes')
        if db.handle_conflicting_output_tables(['network_edge_attributes', 'network_edge_export', 'network_node_attributes']):
            params = {  # TODO: @CW: check hard-coded vs. dynamic table names -> settings; also preferably use common data schema - e.g. to avoid providing combined schema + table identifiers
                'schema_network': schema,
                'schema_data': self.db_settings.entities.data_schema,
                'table_dem': db.use_if_exists('dem', self.db_settings.entities.data_schema),
                'table_noise': db.use_if_exists('noise', self.db_settings.entities.data_schema),
                'column_noise': 'noise',  # TODO: get from settings file
                'table_building': db.use_if_exists('building', self.db_settings.entities.data_schema),
                'table_crossing': db.use_if_exists('crossing', self.db_settings.entities.data_schema),
                'table_facility': db.use_if_exists('facility', self.db_settings.entities.data_schema),
                'table_greenness': db.use_if_exists('greenness', self.db_settings.entities.data_schema),
                'table_water': db.use_if_exists('water', self.db_settings.entities.data_schema),
                'table_parking': db.use_if_exists('parking', self.db_settings.entities.data_schema),
                'table_sights': db.use_if_exists('sights', self.db_settings.entities.data_schema),
                'source_attributes': build_source_attributes_sql(db, schema, export_settings, GIP_DEFAULT_SOURCE_ATTRIBUTES, "gip_")
            }
            if params["table_dem"] is not None:
                h.majorInfo("WARNING: You provided a DEM file. However, for GIP attribute calculation only the elevation data contained in the GIP dataset is used. Your provided DEM is ignored.")
            db.execute_template_sql_from_file("gip_attributes", params)
            db.commit()
        h.logEndTask()

        # close database connection
        h.log('closing database connection')
        db.close()


class Gip2AttributesStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict, export_settings: dict = None):
        h.info('attributes step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.log('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.schema = schema

        # create functions
        h.log('create functions')
        db.execute_sql_from_file("gip2_calculate_bicycle_infrastructure", "sql/functions")
        db.execute_sql_from_file("gip2_calculate_pedestrian_infrastructure", "sql/functions")
        db.execute_sql_from_file("gip2_calculate_road_category", "sql/functions")
        db.commit()

        # execute "gip2_attributes"
        h.logBeginTask('execute "gip2_attributes"')
        if db.handle_conflicting_output_tables(['network_edge_attributes', 'network_edge_export', 'network_node_attributes']):
            params = {  # TODO: @CW: check hard-coded vs. dynamic table names -> settings; also preferably use common data schema - e.g. to avoid providing combined schema + table identifiers
                'schema_network': schema,
                'schema_data': self.db_settings.entities.data_schema,
                'table_dem': db.use_if_exists('dem', self.db_settings.entities.data_schema),
                'table_noise': db.use_if_exists('noise', self.db_settings.entities.data_schema),
                'column_noise': 'noise',  # TODO: get from settings file
                'table_building': db.use_if_exists('building', self.db_settings.entities.data_schema),
                'table_crossing': db.use_if_exists('crossing', self.db_settings.entities.data_schema),
                'table_facility': db.use_if_exists('facility', self.db_settings.entities.data_schema),
                'table_greenness': db.use_if_exists('greenness', self.db_settings.entities.data_schema),
                'table_water': db.use_if_exists('water', self.db_settings.entities.data_schema),
                'table_parking': db.use_if_exists('parking', self.db_settings.entities.data_schema),
                'table_sights': db.use_if_exists('sights', self.db_settings.entities.data_schema),
                'source_attributes': build_source_attributes_sql(db, schema, export_settings, GIP2_DEFAULT_SOURCE_ATTRIBUTES, "gip_")
            }
            if params["table_dem"] is not None:
                h.majorInfo("WARNING: You provided a DEM file. However, for GIP attribute calculation only the elevation data contained in the GIP dataset is used. Your provided DEM is ignored.")
            db.execute_template_sql_from_file("gip2_attributes", params)
            db.commit()
        h.logEndTask()

        # close database connection
        h.log('closing database connection')
        db.close()


class OsmAttributesStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict, export_settings: dict = None):
        h.info('attributes step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.log('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.schema = schema

        # create functions
        h.log('create functions')
        db.execute_sql_from_file("osm_calculate_access_bicycle", "sql/functions")
        db.execute_sql_from_file("osm_calculate_access_car", "sql/functions")
        db.execute_sql_from_file("osm_calculate_access_pedestrian", "sql/functions")
        db.commit()

        # execute "osm_attributes"
        h.logBeginTask('execute "osm_attributes"')
        if db.handle_conflicting_output_tables(['network_edge_attributes', 'network_edge_export', 'network_node_attributes']):
            params = {
                # TODO: harmonize schema + load table names from dbEntitySettings (which are populated / overwritten by read values from settings file)
                'schema_network': schema,
                'schema_data': self.db_settings.entities.data_schema,
                'table_dem': db.use_if_exists('dem', self.db_settings.entities.data_schema),
                'table_noise': db.use_if_exists('noise', self.db_settings.entities.data_schema),
                'column_noise': 'noise',  # TODO: get from settings file
                'table_building': db.use_if_exists('building', self.db_settings.entities.data_schema),
                'table_crossing': db.use_if_exists('crossing', self.db_settings.entities.data_schema),
                'table_facility': db.use_if_exists('facility', self.db_settings.entities.data_schema),
                'table_greenness': db.use_if_exists('greenness', self.db_settings.entities.data_schema),
                'table_water': db.use_if_exists('water', self.db_settings.entities.data_schema),
                'table_parking': db.use_if_exists('parking', self.db_settings.entities.data_schema), #TODO: check if this works with file import
                'table_sights': db.use_if_exists('sights', self.db_settings.entities.data_schema),
                'target_srid': GlobalSettings.get_target_srid(),
                'source_attributes': build_source_attributes_sql(db, schema, export_settings, OSM_DEFAULT_SOURCE_ATTRIBUTES, "osm_")
            }
            db.execute_template_sql_from_file("osm_attributes", params)
            db.commit()
        h.logEndTask()

        # close database connection
        h.log('closing database connection')
        db.close()


def create_attributes_step(db_settings: DbSettings, import_type: str):
    if import_type.lower() == InputType.GIP.value.lower():
        return GipAttributesStep(db_settings)
    if import_type.lower() == InputType.GIP2.value.lower():
        return Gip2AttributesStep(db_settings)
    if import_type.lower() == InputType.OSM.value.lower():
        return OsmAttributesStep(db_settings)
    raise NotImplementedError(f"import type '{import_type}' not implemented")
