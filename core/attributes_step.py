import toolbox.helper as h
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings, InputType
from toolbox.dbhelper import PostgresConnection


class GipAttributesStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict):
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
                'table_water': db.use_if_exists('water', self.db_settings.entities.data_schema)
            }
            if params["table_dem"] is not None:
                h.majorInfo("WARNING: You provided a DEM file. However, for GIP attribute calculation only the elevation data contained in the GIP dataset is used. Your provided DEM is ignored.")
            db.execute_template_sql_from_file("gip_attributes", params)
            db.commit()
        h.logEndTask()

        # close database connection
        h.log('closing database connection')
        db.close()


class OsmAttributesStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict):
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
                'target_srid': GlobalSettings.get_target_srid()
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
    if import_type.lower() == InputType.OSM.value.lower():
        return OsmAttributesStep(db_settings)
    raise NotImplementedError(f"import type '{import_type}' not implemented")
