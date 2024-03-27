import os
import re
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
    access_car: False
    access_bike: False
    access_walk: False

    def __init__(self, base_path: str, definition: dict):
        self.profile_name = definition.get('profile_name')
        filename = os.path.join(base_path, definition.get('filename'))
        self.access_car = h.has_keys(definition, ['filter_access_car']) and definition['filter_access_car']
        self.access_bike = h.has_keys(definition, ['filter_access_bike']) and definition['filter_access_bike']
        self.access_walk = h.has_keys(definition, ['filter_access_walk']) and definition['filter_access_walk']
        # if none of the mode access filters are set, then enable index computation for all modes
        if not (self.access_car or self.access_bike or self.access_walk):
            self.access_car = self.access_bike = self.access_walk = True
        with open(filename) as file:
            self.profile = yaml.safe_load(file)


def load_profiles(base_path: str, profile_definitions: dict):
    return [ModeProfile(base_path, definition) for definition in profile_definitions]

def _build_sql_overrides(overrides_yml: dict) -> str:
    # load yml: extract output details and prepare target variable names
    indicator_name = h.get_safe_name(overrides_yml.get('indicator'))
    h.require_keys(overrides_yml, ["output"], f"No 'output' key provided in overrides definition for '{indicator_name}'.")
    out = overrides_yml.get("output")
    h.require_keys(out, ["type"], f"'output' key has no 'type' in overrides definition for '{indicator_name}'.")
    out_type = out.get("type")
    assignment_targets = []
    if out_type == "index":
        assignment_targets.append("index")
    elif out_type == "weight":
        if h.has_keys(out, ["for"]):
            ft = out.get("for")
            if type(ft) == str:
                assignment_targets.append(f"{h.get_safe_name(ft)}_weight")
            elif type(ft) == list:
                for t in ft:
                    assignment_targets.append(f"{h.get_safe_name(t)}_weight")
    else:
        raise Exception(f"Unknown output type '{out_type}' provided in overrides definition for '{indicator_name}'.")
    # compile value assignment SQL
    assignment_sql = ""
    for a_target in assignment_targets:
        assignment_sql += f"{a_target} := temp; \n"
    # delete output details and description from yml (for function compatibility)
    del overrides_yml['output']
    del overrides_yml['description']
    # compile value mappings
    value_assignments = _build_sql_indicator_mapping_internal_(overrides_yml, "", force_default_value = True, def_value = -1)
    # compile full indicator SQL around indicator mapping code
    sql: str = f"""
        temp :=
            {value_assignments};
        IF NOT temp < 0 THEN
            {assignment_sql}
            {"return; " if out_type == "index" else ""}
        END IF;
        """
    # compile result into template
    return sql

def _build_sql_indicator_mapping_internal_(indicator_yml: dict, name_hierarchy: str = "", force_default_value: bool = False, def_value = None) -> str:
    indicator_name = h.get_safe_name(indicator_yml.get('indicator'))
    full_name = name_hierarchy + indicator_name
    h.debugLog(f"parsing YAML for ind. '{full_name}' \tRaw input: {indicator_yml}")
    value_assignments = "CASE \n"
    add_default_value: bool = force_default_value
    default_value = def_value

    # check type of mapping
    del indicator_yml['indicator']
    keys = indicator_yml.keys()
    if len(keys) != 1:
        raise Exception(f"Exactly one indicator mapping key is needed for indicator '{full_name}'. Please update your mode profile file accordingly.")
    k = list(keys)[0]
    contents = indicator_yml.get(k)
    if k not in ["mapping", "classes"]:
        raise Exception(f"You provided an unknown indicator mapping '{k}' for indicator '{full_name}'. Please update your mode profile file accordingly.")
    # parse each of the given keys
    for key in contents:
        # handle special assignment value types
        v = contents[key]
        h.debugLog(f"got mapping: {key}: {v} (type: {type(key)}:{type(v)})")
        if type(v) == dict:
            # parse dict recursively -> add result to value_assignments (nested CASE...END)
            v = _build_sql_indicator_mapping_internal_(v, f"{full_name}.", force_default_value, def_value)
        elif v is None:
            v = "NULL"
        elif not h.is_numeric(v):
            raise Exception(f"Only numeric value assignments are allowed for indicator mappings. Please update indicator '{full_name}' for '{key}'.")
        # handle special cases and (in last step) default cases for key types/values
        # special case of NULL value key
        if key is None:
            value_assignments += f"WHEN {indicator_name} IS NULL THEN {v}\n"
        # handle special case of default value (added last)
        elif str(key) == "_default_":
            add_default_value = True
            default_value = v
        # handle lists
        elif str(key).startswith("{") and str(key).endswith("}"):
            # list of Strings or numeric values
            s = str(key)[1:-1]
            slist = s.split(',')
            # if list contains at least one non-numeric value, interpret as list of strings
            cnt = sum([1 for val in slist if not h.str_is_numeric_only(val)])
            if cnt > 0:
                # String
                value_assignments += f"""WHEN {indicator_name} IN ('{"', '".join([h.get_safe_string(v.strip()) for v in slist])}') THEN {v}\n"""
            else:
                # numeric
                value_assignments += f"WHEN {indicator_name} IN ({', '.join([str(h.str_to_numeric(v.strip())) for v in slist])}) THEN {v}\n"
        # specific handling depending on type (mapping / classes)
        elif k == "mapping":
            if h.is_numeric(key) or type(key) == bool:
                value_assignments += f"WHEN {indicator_name} = {key} THEN {v}\n"
            else:
                value_assignments += f"WHEN {indicator_name} = '{h.get_safe_string(key)}' THEN {v}\n"
        elif k == "classes":
            # split key into op. and class value
            kstr = str(key)
            cv = h.str_to_numeric(kstr)
            if cv is None:
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
            raise Exception(f"Unexpected configuration received for indicator '{indicator_name}', key '{key}'.")
    
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
            # parse profile definition: generate SQL for overrides (indicator weights or index)
            h.info(f'parsing value overrides for profile "{profile_name}"...')
            overrides_sql = ""
            for override in p.profile['overrides']:
                overrides_sql += _build_sql_overrides(override)
            h.debugLog(f"compiled overrides SQL: \n\n{overrides_sql}")
            
            # profile-specific function registration
            h.info(f'register index function for profile "{profile_name}"...')
            f_params = {
                'compute_explanation': settings and h.has_keys(settings, ['compute_explanation']) and settings['compute_explanation'],
                'indicator_mappings': indicator_mapping_sql,
                'overrides': overrides_sql
            }
            db.execute_template_sql_from_file("calculate_index", f_params, template_subdir="sql/functions/")
            # calculate index for currrent profile
            h.info('calculate index_' + profile_name)
            params = {
                'schema_network': schema,
                'profile_name': profile_name,
                'compute_explanation': settings and h.has_keys(settings, ['compute_explanation']) and settings['compute_explanation'],
                'access_car': p.access_car,
                'access_bike': p.access_bike,
                'access_walk': p.access_walk,
            }
            params.update(indicator_weights)
            print(params)
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
