import toolbox.helper as h
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings, InputType
from toolbox.dbhelper import PostgresConnection


class GipNetworkStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict):
        h.info('network step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.log('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.init_extensions_and_schema(schema)

        # execute "gip_network"
        h.logBeginTask('execute "gip_network"')
        if db.handle_conflicting_output_tables(['network_edge', 'network_node']):
            params = {
                'schema_network': schema,
                'schema_data': self.db_settings.entities.data_schema,
                'target_srid': GlobalSettings.get_target_srid()
            }
            db.execute_template_sql_from_file("gip_network", params)
            db.commit()
        h.logEndTask()

        # close database connection
        h.log('closing database connection')
        db.close()


class OsmNetworkStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict):
        h.info('network step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.log('connecting to database...')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.connect()
        db.init_extensions_and_schema(schema)

        # create functions
        h.log('create functions')
        db.execute_sql_from_file("osm_delete_dangling_edges", "sql/functions")
        db.commit()

        # execute "osm_network"
        h.logBeginTask('execute "osm_network"')
        if db.handle_conflicting_output_tables(['network_edge', 'network_node']):
            params = {
                'schema_network': schema,
                'schema_data': self.db_settings.entities.data_schema,
                'target_srid': GlobalSettings.get_target_srid(),
                'include_rail': settings and h.has_keys(settings, ['include_rail']) and settings['include_rail'],
                'include_aerialway': settings and h.has_keys(settings, ['include_aerialway']) and settings['include_aerialway']
            }
            db.execute_template_sql_from_file("osm_network", params)
            db.commit()
        h.logEndTask()

        # close database connection
        h.log('closing database connection')
        db.close()


def create_network_step(db_settings: DbSettings, import_type: str):
    if import_type.lower() == InputType.GIP.value.lower():
        return GipNetworkStep(db_settings)
    if import_type.lower() == InputType.OSM.value.lower():
        return OsmNetworkStep(db_settings)
    raise NotImplementedError(f"import type '{import_type}' not implemented")
