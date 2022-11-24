import os.path
import toolbox.helper as h
import yaml
from settings import DbSettings
from toolbox.dbhelper import PostgresConnection
from typing import List


class WeightDefinition:
    profile_name: str
    filename: str

    def __init__(self, profile_name: str, filename: str):
        self.profile_name = profile_name
        self.filename = filename


class Weight:
    profile_name: str
    weights: dict = {}

    def __init__(self, base_path: str, definition: dict):
        self.profile_name = definition.get('profile_name')
        filename = os.path.join(base_path, definition.get('filename'))
        with open(filename) as file:
            self.weights = yaml.safe_load(file)


def load_weights(base_path: str, weight_definitions: dict):
    return [Weight(base_path, definition) for definition in weight_definitions]


def generate_index(db_settings: DbSettings, weights: List[Weight]):
    schema = db_settings.entities.network_schema

    # open database connection
    h.info('open database connection')
    db = PostgresConnection.from_settings_object(db_settings)

    # set search path
    h.log('set search path')
    db.schema = schema

    # create functions
    h.log('create functions')
    db.execute_sql_from_file("calculate_index", "sql/functions")

    # calculate index
    h.logBeginTask("compute index columns for given profiles")
    if db.handle_conflicting_output_tables(['network_edge_index']):
        for w in weights:
            profile_name = w.profile_name
            weights = w.weights['weights']
            h.info('calculate index_' + profile_name)
            params = {
                'schema_meta_net': db_settings.entities.network_schema,
                'column_index_ft': 'index_' + profile_name + '_ft',
                'column_index_tf': 'index_' + profile_name + '_tf'
            }
            params.update(weights)
            db.execute_template_sql_from_file("index", params)
    h.logEndTask()

    # create tables "edges" and "nodes"
    h.logBeginTask('create tables "export_network_edge" and "export_network_node"')
    if db.handle_conflicting_output_tables(['export_network_edge', "export_network_node"]):
        params = {
            'schema_meta_net': schema
        }
        db.execute_template_sql_from_file("export", params)
    h.logEndTask()

    # close database connection
    h.log('close database connection')
    db.close()
