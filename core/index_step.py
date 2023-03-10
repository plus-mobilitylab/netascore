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


def generate_index(db_settings: DbSettings, weights: List[Weight], settings: dict):
    schema = db_settings.entities.network_schema

    # open database connection
    h.info('open database connection')
    db = PostgresConnection.from_settings_object(db_settings)

    # set search path
    h.log('set search path')
    db.schema = schema

    # create functions
    ## this now happens in the "calculate index step" (re-defining functions based on mode profile and settings)

    # calculate index
    h.logBeginTask("compute index columns for given profiles")
    if db.handle_conflicting_output_tables(['network_edge_index']):
        for w in weights:
            profile_name = w.profile_name
            indicator_weights = w.weights['weights']
            # profile-specific function registration
            h.info(f'register index function for profile "{profile_name}"...')
            f_params = {
                'compute_explanation': settings and h.has_keys(settings, ['compute_explanation']) and settings['compute_explanation']
            }
            db.execute_template_sql_from_file("calculate_index", f_params, template_subdir="sql/functions/")
            # calculate index for currrent profile
            h.info('calculate index_' + profile_name)
            params = {
                'schema_network': schema,
                'profile_name': profile_name,
                'compute_explanation': settings and h.has_keys(settings, ['compute_explanation']) and settings['compute_explanation']
            }
            params.update(indicator_weights)
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

    # create views for routing
    # db.execute('''
    #     CREATE OR REPLACE VIEW network_car AS (
    #         SELECT edge_id AS id,
    #                from_node AS source,
    #                to_node AS target,
    #                CASE WHEN access_car_ft = false THEN -1 -- no access
    #                     ELSE length::numeric
    #                END AS cost,
    #                CASE WHEN access_car_tf = false THEN -1 -- no access
    #                     ELSE length::numeric
    #                END AS reverse_cost
    #         FROM export_edge
    #         WHERE access_car_ft OR access_car_tf
    #     );
    #
    #     CREATE OR REPLACE VIEW network_bike AS (
    #         SELECT edge_id AS id,
    #                from_node AS source,
    #                to_node AS target,
    #                ((CASE WHEN NOT access_bicycle_ft AND NOT access_pedestrian_ft THEN -1 -- no access
    #                       WHEN NOT access_bicycle_ft AND access_pedestrian_ft THEN 3 -- pedestrian access
    #                       WHEN bridge THEN 3 -- bridge
    #                       ELSE 1 - index_bike_ft
    #                  END + 1) * (5 - 1) - (5 - 2)) * length::numeric AS cost,
    #                ((CASE WHEN NOT access_bicycle_tf AND NOT access_pedestrian_tf THEN -1 -- no access
    #                       WHEN NOT access_bicycle_tf AND access_pedestrian_tf THEN 3 -- pedestrian access
    #                       WHEN bridge THEN 3 -- bridge
    #                       ELSE 1 - index_bike_tf
    #                  END + 1) * (5 - 1) - (5 - 2)) * length::numeric AS reverse_cost
    #         FROM export_edge
    #         WHERE access_bicycle_ft OR access_bicycle_tf OR
    #               access_pedestrian_ft OR access_pedestrian_tf
    #     );
    #
    #     CREATE OR REPLACE VIEW network_walk AS (
    #         SELECT edge_id AS id,
    #                from_node AS source,
    #                to_node AS target,
    #                ((CASE WHEN NOT access_pedestrian_ft THEN -1 -- no access
    #                       WHEN bridge THEN 0.6 -- bridge
    #                       ELSE index_walk_ft
    #                  END + 1) * (5 - 1) - (5 - 2)) * length::numeric AS cost,
    #                ((CASE WHEN NOT access_pedestrian_tf THEN -1 -- no access
    #                       WHEN bridge THEN 0.6 -- bridge
    #                       ELSE index_walk_tf
    #                  END + 1) * (5 - 1) - (5 - 2)) * length::numeric AS reverse_cost
    #         FROM export_edge
    #         WHERE access_pedestrian_ft OR access_pedestrian_tf
    #     );
    # ''')
    # db.commit()

    # close database connection
    h.log('close database connection')
    db.close()
