import re
import sys

import toolbox.helper as h
from core import dataset_registry as registry
from core import metadata
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
    h.info(f"adding {len(parts)} source attribute(s) to the export")
    return "".join(f", {p}" for p in parts)


# input datasets in the shared data schema: (dataset / table name, indicator)
INPUT_DATASETS = [('dem', 'gradient'), ('noise', 'noise'), ('building', 'buildings'), ('crossing', 'crossings'), ('facility', 'facilities'),
                  ('greenness', 'greenness'), ('water', 'water'), ('parking', 'parking'), ('sights', 'sights')]


def prepare_input_datasets(db: PostgresConnection, network_schema: str, data_schema: str, skip: list = None) -> dict:
    """Checks the input datasets against the network of the current case using the dataset registry and returns the
    template parameters 'table_<dataset>' (None: not used) and 'coverage_<dataset>' (True: dataset covers only parts of the network).
    - datasets that do not cover the network at all are not used (warning)
    - for datasets covering only parts of the network, edges outside the coverage get no indicator value (NULL; table 'edge_coverage')
    - datasets in a different coordinate system are transformed (temporary table '<dataset>_transformed' in the network schema)"""
    target_srid = GlobalSettings.get_target_srid()
    params = {}
    usage = []  # use of the datasets (stored as metadata of the run)
    db.execute(f"DROP TABLE IF EXISTS {network_schema}.edge_coverage; CREATE TABLE {network_schema}.edge_coverage AS SELECT edge_id FROM {network_schema}.network_edge; "
               f"ALTER TABLE {network_schema}.edge_coverage ADD PRIMARY KEY (edge_id);")
    for dataset, indicator in INPUT_DATASETS:
        params[f"table_{dataset}"] = None
        params[f"coverage_{dataset}"] = False
        if db.use_if_exists(dataset, data_schema) is None:
            continue
        row = {'dataset': dataset, 'indicator': indicator, 'status': 'used', 'network_share_covered': None, 'transformed_crs': False, 'note': None}
        usage.append(row)
        if dataset in (skip or []):
            row.update(status='not_used', note='not used for this import type')
            continue
        entry = registry.get_registered(db, data_schema, dataset)
        if entry is None:
            h.majorInfo(f"WARNING: dataset '{dataset}' has unknown origin (imported with an older version of NetAScore or import not completed) - "
                        f"it is used without checking its coordinate system and coverage.")
            params[f"table_{dataset}"] = dataset
            row.update(note='unknown origin - coordinate system and coverage not checked')
            continue
        # share of the network (length) within the coverage of the dataset (unknown coverage: assumed to cover the network)
        share = 1.0
        if entry['has_coverage']:
            share = db.query_one(f"""
                WITH c AS (SELECT ST_Transform(coverage, %(srid)s) AS geom FROM {data_schema}.{registry.REGISTRY_TABLE} WHERE dataset = %(dataset)s)
                SELECT coalesce(sum(e.length) FILTER (WHERE ST_Intersects(e.geom, c.geom)) / nullif(sum(e.length), 0), 0)
                FROM {network_schema}.network_edge e, c;""", {'srid': target_srid, 'dataset': dataset})[0]
            share = float(share)
            row['network_share_covered'] = round(share, 4)
        if share == 0:
            h.majorInfo(f"WARNING: dataset '{dataset}' (imported for case '{entry['case_id']}') does not cover the network of this case - "
                        f"the indicator '{indicator}' is not computed, index robustness will decrease.")
            row.update(status='not_used', note='does not cover the network')
            continue
        if share < 1:
            h.majorInfo(f"WARNING: dataset '{dataset}' covers only {share * 100:.1f} % of the network (length) - "
                        f"edges outside its coverage are assigned no value for the indicator '{indicator}' and their index robustness will decrease.")
            db.execute(f"""
                ALTER TABLE {network_schema}.edge_coverage ADD COLUMN {dataset} boolean;
                UPDATE {network_schema}.edge_coverage ec SET {dataset} = ST_Intersects(e.geom, c.geom)
                FROM {network_schema}.network_edge e,
                     (SELECT ST_Transform(coverage, %(srid)s) AS geom FROM {data_schema}.{registry.REGISTRY_TABLE} WHERE dataset = %(dataset)s) c
                WHERE e.edge_id = ec.edge_id;""", {'srid': target_srid, 'dataset': dataset})
            params[f"coverage_{dataset}"] = True
            row.update(status='partial', note='no indicator value for edges outside the coverage')
        params[f"table_{dataset}"] = dataset
        # vector data in a different coordinate system (e.g. imported for another case): use a transformed copy
        # (the DEM keeps its coordinate system - the network is transformed temporarily for computing gradients - for better performance.)
        if dataset != 'dem' and entry['srid'] is not None and entry['srid'] != target_srid:
            h.info(f"dataset '{dataset}' is stored in EPSG:{entry['srid']} - transforming it to EPSG:{target_srid} for this case")
            db.execute(f"""
                DROP TABLE IF EXISTS {network_schema}.{dataset}_transformed;
                CREATE TABLE {network_schema}.{dataset}_transformed AS SELECT * FROM {data_schema}.{dataset};
                ALTER TABLE {network_schema}.{dataset}_transformed ALTER COLUMN geom TYPE geometry USING ST_Transform(geom, %(srid)s);
                CREATE INDEX {dataset}_transformed_geom_idx ON {network_schema}.{dataset}_transformed USING gist (geom);""", {'srid': target_srid})
            params[f"table_{dataset}"] = f"{dataset}_transformed"
            row.update(transformed_crs=True)
    db.commit()
    metadata.record_datasets(db, network_schema, usage, data_schema)
    return params


def cleanup_input_datasets(db: PostgresConnection, network_schema: str) -> None:
    """Removes the temporary tables created by prepare_input_datasets()."""
    tables = ['edge_coverage'] + [f"{dataset}_transformed" for dataset, _ in INPUT_DATASETS]
    db.execute(f"DROP TABLE IF EXISTS {', '.join(f'{network_schema}.{t}' for t in tables)};")
    db.commit()


class GipAttributesStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict, export_settings: dict = None):
        h.debugLog('attributes step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.debugLog('connecting to database...')
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
                **prepare_input_datasets(db, schema, self.db_settings.entities.data_schema, skip=['dem']),  # GIP: elevation data from GIP
                'source_attributes': build_source_attributes_sql(db, schema, export_settings, GIP_DEFAULT_SOURCE_ATTRIBUTES, "gip_")
            }
            db.execute_template_sql_from_file("gip_attributes", params)
            db.commit()
            cleanup_input_datasets(db, schema)
        h.logEndTask()

        # close database connection
        h.debugLog('closing database connection')
        db.close()


class Gip2AttributesStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict, export_settings: dict = None):
        h.debugLog('attributes step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.debugLog('connecting to database...')
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
                **prepare_input_datasets(db, schema, self.db_settings.entities.data_schema, skip=['dem']),  # GIP: elevation data from GIP
                'source_attributes': build_source_attributes_sql(db, schema, export_settings, GIP2_DEFAULT_SOURCE_ATTRIBUTES, "gip_")
            }
            db.execute_template_sql_from_file("gip2_attributes", params)
            db.commit()
            cleanup_input_datasets(db, schema)
        h.logEndTask()

        # close database connection
        h.debugLog('closing database connection')
        db.close()


class OsmAttributesStep(DbStep):
    def __init__(self, db_settings: DbSettings):
        super().__init__(db_settings)

    def run_step(self, settings: dict, export_settings: dict = None):
        h.debugLog('attributes step')
        h.log(f"using import settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema

        # open database connection
        h.debugLog('connecting to database...')
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
                **prepare_input_datasets(db, schema, self.db_settings.entities.data_schema),
                'target_srid': GlobalSettings.get_target_srid(),
                'source_attributes': build_source_attributes_sql(db, schema, export_settings, OSM_DEFAULT_SOURCE_ATTRIBUTES, "osm_")
            }
            db.execute_template_sql_from_file("osm_attributes", params)
            db.commit()
            cleanup_input_datasets(db, schema)
        h.logEndTask()

        # close database connection
        h.debugLog('closing database connection')
        db.close()


def create_attributes_step(db_settings: DbSettings, import_type: str):
    if import_type.lower() == InputType.GIP.value.lower():
        return GipAttributesStep(db_settings)
    if import_type.lower() == InputType.GIP2.value.lower():
        return Gip2AttributesStep(db_settings)
    if import_type.lower() == InputType.OSM.value.lower():
        return OsmAttributesStep(db_settings)
    raise NotImplementedError(f"import type '{import_type}' not implemented")
