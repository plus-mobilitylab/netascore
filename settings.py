import os
from dataclasses import dataclass
from enum import Enum


class InputType(Enum):
    OSM = "OSM"
    GIP = "GIP"


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
    on_existing: str

    def __post_init__(self):
        self.entities: DbEntitySettings = DbEntitySettings(GlobalSettings.case_id)

    @staticmethod
    def from_dict(settings_template: dict):
        host = settings_template.get('host', 'netascore-db')
        port = settings_template.get('port', 5432)
        dbname = settings_template.get('dbname', 'postgres')
        username = settings_template.get('username', '')
        password = settings_template.get('password', '')
        on_existing = settings_template.get('on_existing', 'abort')

        if len(username) == 0:
            username = os.getenv('DB_USERNAME', '')
        if len(password) == 0:
            password = os.getenv('DB_PASSWORD', '')

        if len(username) == 0:
            print('warn: DB_USERNAME not set')

        if len(password) == 0:
            print('warn: DB_PASSWORD not set')

        return DbSettings(host, port, dbname, username, password, on_existing)


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
