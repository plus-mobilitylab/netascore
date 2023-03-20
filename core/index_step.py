import os
from markupsafe import re
import yaml

import toolbox.helper as h
from settings import DbSettings
from toolbox.dbhelper import PostgresConnection
from typing import List


class ProfileDefinition:
    profile_name: str
    filename: str

    def __init__(self, profile_name: str, filename: str):
        self.profile_name = profile_name
        self.filename = filename


class ModeProfile:
    profile_name: str
    profile: dict = {}

    def __init__(self, base_path: str, definition: dict):
        self.profile_name = definition.get('profile_name')
        filename = os.path.join(base_path, definition.get('filename'))
        with open(filename) as file:
            self.profile = yaml.safe_load(file)


def load_profiles(base_path: str, profile_definitions: dict):
    return [ModeProfile(base_path, definition) for definition in profile_definitions]


def _build_sql_indicator_mapping_internal_(indicator_yml: dict, name_hierarchy: str = "") -> str:
    indicator_name = h.get_safe_name(indicator_yml.get('indicator'))
    full_name = name_hierarchy + indicator_name
    h.debugLog(f"parsing YAML for ind. '{full_name}' \tRaw input: {indicator_yml}")
    value_assignments = "CASE \n"
    add_default_value: bool = False
    default_value = None

    # check type of mapping
    del indicator_yml['indicator']
    keys = indicator_yml.keys()
    if len(keys) != 1:
        raise Exception(f"Exactly one indicator mapping key is needed for indicator '{full_name}'. Please update your mode profile file accordingly.")
    k = list(keys)[0]
    contents = indicator_yml.get(k)

    if k == "mapping":
        for key in contents:
            v = contents[key]
            h.debugLog(f"got mapping: {key}: {v} (type: {type(key)}:{type(v)})")
            if type(v) == dict:
                # parse dict recursively -> add result to value_assignments (nested CASE...END)
                v = _build_sql_indicator_mapping_internal_(v, f"{full_name}.")
            elif v is None:
                v = "NULL"
            elif not h.is_numeric(v):
                raise Exception(f"Only numeric value assignments are allowed for indicator mappings. Please update indicator '{full_name}' for '{key}'.")
            # append current assignment
            # handle special case of test for NULL values
            if key is None:
                value_assignments += f"WHEN {indicator_name} IS NULL THEN {v}\n"
            # handle special case of default value (added last)
            elif str(key) == "_default_":
                add_default_value = True
                default_value = v
            else:
                value_assignments += f"WHEN {indicator_name} = '{h.get_safe_string(key)}' THEN {v}\n"
    elif k == "classes":
        for key in contents:
            v = contents[key]
            h.debugLog(f"got mapping: {key}: {v} (type: {type(key)}:{type(v)})")
            if type(v) == dict:
                # parse dict recursively -> add result to value_assignments (nested CASE...END)
                v = _build_sql_indicator_mapping_internal_(v, f"{full_name}.")
            elif v is None:
                v = "NULL"
            elif not h.is_numeric(v):
                raise Exception(f"Only numeric value assignments are allowed for indicator mappings. Please update indicator '{full_name}' for '{key}'.")
            # first: handle special case of NULL value
            if key is None:
                value_assignments += f"WHEN {indicator_name} IS NULL THEN {v}\n"
            # handle special case of default value (added last)
            elif str(key) == "_default_":
                add_default_value = True
                default_value = v
            else:
                # split key into op. and class value
                kstr = str(key)
                cv = re.sub("[^0-9.\-]", "", kstr) # extract value
                if cv.find(".") > -1:
                    cv = float(cv)
                elif len(cv) > 0:
                    cv = int(cv)
                else:
                    raise Exception(f"For class-based indicator value assignments, a numeric class value must be specified. Indicator '{full_name}', key '{key}'.")
                op = "=" # default: equals
                opstr = re.sub("[^a-zA-Z]", "", kstr)
                if opstr == "g":
                    op = ">"
                elif opstr == "ge":
                    op = ">="
                elif opstr == "l":
                    op = "<"
                elif opstr == "le":
                    op = "<="
                elif opstr == "e":
                    op = "="
                elif opstr == "ne":
                    op = "<>"
                # append current assignment
                value_assignments += f"WHEN {indicator_name} {op} {cv} THEN {v}\n"
    else:
        raise Exception(f"You provided an unknown indicator mapping '{k}' for indicator '{full_name}'. Please update your mode profile file accordingly.")
    # add default value assignment if specified
    if add_default_value:
        value_assignments += f"ELSE {default_value} \n"
    # close this indicator mapping CASE statement
    value_assignments += "END \n"
    return value_assignments

def _build_sql_indicator_mapping(indicator_yml: dict) -> str:
    indicator_name = h.get_safe_name(indicator_yml.get('indicator'))
    value_assignments = _build_sql_indicator_mapping_internal_(indicator_yml)
    # compile full indicator SQL around indicator mapping code
    sql: str = f"""
        IF {indicator_name} IS NOT NULL AND {indicator_name}_weight IS NOT NULL THEN
            indicator :=
                {value_assignments};
            weight := {indicator_name}_weight / weights_sum;
            index := index + indicator * weight;
            indicator_weights := array_append(indicator_weights, ('{indicator_name}', indicator * weight)::indicator_weight);
        END IF;"""
    return sql

def generate_index(db_settings: DbSettings, profiles: List[ModeProfile], settings: dict):
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
        for p in profiles:
            profile_name = p.profile_name
            indicator_weights = p.profile['weights']
            # parse profile definition: generate SQL for indicator value assignments
            h.info(f'parsing indicator value mapping for profile "{profile_name}"...')
            indicator_mapping_sql = ""
            for indicator in p.profile['indicator_mapping']:
                indicator_mapping_sql += _build_sql_indicator_mapping(indicator)
            h.debugLog(f"compiled indicator mapping SQL: \n\n{indicator_mapping_sql}")
            
            # profile-specific function registration
            h.info(f'register index function for profile "{profile_name}"...')
            f_params = {
                'compute_explanation': settings and h.has_keys(settings, ['compute_explanation']) and settings['compute_explanation'],
                'indicator_mappings': indicator_mapping_sql
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
