import os
import yaml

import toolbox.helper as h
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
                'schema_network': schema,
                'profile_name': profile_name
            }
            params.update(weights)
            db.execute_template_sql_from_file("index", params)
    h.logEndTask()

    # create tables "edges" and "nodes"
    h.logBeginTask('create tables "export_edge" and "export_node"')
    if db.handle_conflicting_output_tables(['export_edge', "export_node"]):
        params = {
            'schema_network': schema
        }
        db.execute_template_sql_from_file("export", params)
    h.logEndTask()

    # check for null columns
    rows = db.query_all("SELECT attname FROM pg_stats WHERE schemaname = %s AND tablename = %s AND null_frac = 1;", (schema, 'export_edge'))
    if rows:
        h.majorInfo(f"WARNING: The following columns contain only NULL values: {', '.join(str(row[0]) for row in rows)}")

    # close database connection
    h.log('close database connection')
    db.close()
