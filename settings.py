import os

import toolbox.helper as h
from dataclasses import dataclass
from enum import Enum


NETASCORE_VERSION = "2.0.0"


class InputType(Enum):
    OSM = "OSM"
    GIP = "GIP"
    GIP2 = "GIP2"


class GlobalSettings:
    data_directory = "data"
    osm_download_prefix = "osm_download"
    overpass_api_endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://z.overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter"
    ]
    overpass_api_user = "NetAScore-Python"
    # maximum area (km²) of OSM downloads from the Overpass API (larger areas: use an OSM extract, e.g. from Geofabrik)
    overpass_max_area: float = 1500
    default_srid: int = 32633
    custom_srid = None
    def get_target_srid()->int:
        return GlobalSettings.custom_srid or GlobalSettings.default_srid

    case_id = "default_net"


@dataclass
class DbSettings:
    host: str
    port: int
    dbname: str
    username: str
    password: str

    def __post_init__(self):
        self.entities: DbEntitySettings = DbEntitySettings(GlobalSettings.case_id)

    @staticmethod
    def from_dict(settings_template: dict):
        # the database section is optional (defaults to the database inside the Docker container)
        settings_template = settings_template if isinstance(settings_template, dict) else {}
        host = settings_template.get('host') or 'netascore-db'
        port = settings_template.get('port') or 5432
        dbname = settings_template.get('dbname') or 'postgres'
        username = str(settings_template.get('username') or '')
        password = str(settings_template.get('password') or '')
        if settings_template.get('on_existing') is not None:
            h.info("'on_existing' in section 'database' is no longer used: processing steps always replace their outputs."
                   "Use the command line option '--skip' to skip steps; settings for input data: 'on_existing' in sections 'import' and 'optional'.")

        if len(username) == 0:
            username = os.getenv('DB_USERNAME', '')
        if len(password) == 0:
            password = os.getenv('DB_PASSWORD', '')

        if len(username) == 0:
            h.majorInfo('WARNING: no database username given (setting \'username\' or environment variable DB_USERNAME)')

        if len(password) == 0:
            h.majorInfo('WARNING: no database password given (setting \'password\' or environment variable DB_PASSWORD)')

        return DbSettings(host, port, dbname, username, password)


class DbEntitySettings:

    def __init__(self, case_name: str):
        self.case_name: str = case_name
        self.global_schema_prefix: str = "netascore_"
        self.schema_prefix: str = "case_"
        self.data_schema_suffix: str = "data"
        self.table_net: str = "network"
        self.table_net_nodes: str = "network_nodes"             # "network_vertices_pgr" for pgRouting-based workflow
        self.table_net_attributes: str = "network_attributes"
        self.table_net_indicators: str = "network_indicators"
        self.table_net_index: str = "network_modes_index"       # output table with bike/walk/etc. index columns
        self.table_aoi: str = "aoi"
        # self.table_osm_bicycle_routes: str = "osm_bicycle_route_network"
        # self.table_osm_bicycle_routes_lines: str = "osm_bicycle_route_network_line"
        
        self._data_schema: str = None
        self._network_schema: str = None
        self._output_schema: str = None
    
    ### computed properties (e.g. joined with a name, etc.) - can also be manually set instead // getter with default return value and setter ###
    
    # data schema
    def get_data_schema(self) -> str:
        return self._data_schema or f"{self.global_schema_prefix}{self.data_schema_suffix}".lower()

    def set_data_schema(self, schema: str):
        self._data_schema = schema
    data_schema: str = property(get_data_schema, set_data_schema)

    # network schema
    def get_network_schema(self) -> str:
        return self._network_schema or f"{self.global_schema_prefix}{self.schema_prefix}{self.case_name}".lower()

    def set_network_schema(self, schema: str):
        self._network_schema = schema
    network_schema: str = property(get_network_schema, set_network_schema)

    # output schema
    def get_output_schema(self) -> str:
        return self._output_schema or self.network_schema  # defaults to network schema

    def set_output_schema(self, schema: str):
        self._output_schema = schema
    output_schema: str = property(get_output_schema, set_output_schema)


# known keys of the settings file (unknown keys, e.g. typos, are reported as warnings - they are ignored);
# keys of the profile entries and mode profiles are checked when loading the profiles (index step)
SETTINGS_KEYS = {
    'top_level': ['version', 'global', 'database', 'import', 'optional', 'index', 'profiles', 'export'],
    'global': ['target_srid', 'case_id'],
    'database': ['host', 'port', 'dbname', 'username', 'password', 'on_existing'],  # on_existing: no longer used (note)
    'import': {
        'osm': ['type', 'filename', 'on_existing', 'place_name', 'bbox', 'aoi_filename', 'buffer', 'clip', 'interactive',
                'max_download_area', 'include_rail', 'include_aerialway'],
        'gip': ['type', 'filename', 'filename_A', 'on_existing', 'regional_code', 'bbox'],  # filename_A: renamed (note)
        'gip2': ['type', 'filename', 'filename_A', 'on_existing', 'regional_code', 'bbox'],
    },
    'optional': {
        'defaults': ['on_existing', 'clip'],
        'dem': ['filename', 'srid', 'on_existing', 'clip', 'coverage'],
        'noise': ['filename', 'layer', 'column_noise', 'value_mapping', 'on_existing', 'clip', 'coverage'],
        'osm': ['filename', 'on_existing', 'clip'],
        **{dataset: ['filename', 'on_existing', 'clip', 'coverage']
           for dataset in ['building', 'crossing', 'facility', 'greenness', 'water', 'parking', 'sights']},
    },
    'index': ['compute_explanation'],
    'export': ['type', 'filename', 'include_source_attributes'],
}


def warn_unknown_settings(settings: dict) -> None:
    """Reports unknown keys (e.g. typos) in the settings file as warnings - these keys are ignored."""
    if not isinstance(settings, dict):
        return
    h.warn_unknown_keys(settings, SETTINGS_KEYS['top_level'], "settings file")
    for section in ['global', 'database', 'index', 'export']:
        h.warn_unknown_keys(settings.get(section), SETTINGS_KEYS[section], f"section '{section}'")
    import_settings = settings.get('import')
    if isinstance(import_settings, dict):
        import_type = str(import_settings.get('type') or '').lower()
        if import_type in SETTINGS_KEYS['import']:
            h.warn_unknown_keys(import_settings, SETTINGS_KEYS['import'][import_type], f"section 'import' (type '{import_type}')")
    optional = settings.get('optional')
    if isinstance(optional, dict):
        # unknown dataset names are not checked here: these lead to an error in the optional step
        for dataset, dataset_settings in optional.items():
            if dataset in SETTINGS_KEYS['optional']:
                h.warn_unknown_keys(dataset_settings, SETTINGS_KEYS['optional'][dataset], f"section 'optional' > '{dataset}'")
