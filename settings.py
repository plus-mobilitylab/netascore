import os
import re
import subprocess

import toolbox.helper as h
from dataclasses import dataclass
from enum import Enum


NETASCORE_VERSION = "2.0.0"
NETASCORE_REPOSITORY = "https://github.com/plus-mobilitylab/netascore"

_code_state = {}  # cached result of _get_code_state()


def _github_url(remote: str) -> str:
    """HTTPS URL of a GitHub repository given as Git remote (HTTPS or SSH) - None for other hosts."""
    match = re.fullmatch(r"(?:https://|git@|ssh://git@)github\.com[:/](.+?)(?:\.git)?/?", remote.strip())
    return f"https://github.com/{match.group(1)}" if match else None


def _get_code_state() -> dict:
    """Code state of NetAScore: 'commit' - branch and 'git describe' of the Git checkout (e.g. 'dev-main, v1.1.1-144-g37365cd',
    with suffix '-dirty' if there are uncommitted changes) or - without Git history, e.g. in the Docker image - the value of the
    environment variable NETASCORE_COMMIT (set when building the image); 'url' - link to the repository state at the release
    tag or commit on GitHub (e.g. https://github.com/plus-mobilitylab/netascore/tree/v2.0.0);
    'pushed' - whether the commit is on a remote branch. Values are None if unknown (e.g. code downloaded as ZIP)."""
    if _code_state:
        return _code_state
    commit = url = pushed = None
    directory = os.path.dirname(os.path.abspath(__file__))
    git = lambda *args: subprocess.run(["git", *args], cwd=directory, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    try:
        describe = git("describe", "--tags", "--dirty", "--always")
        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        commit = describe if branch in ("", "HEAD") else f"{branch}, {describe}"  # 'HEAD': detached (e.g. a checked out tag)
        try:
            repository = _github_url(git("remote", "get-url", "origin"))  # forks: link to the fork
        except subprocess.SubprocessError:
            repository = NETASCORE_REPOSITORY
        if repository:
            try:  # exactly on a release tag
                url = f"{repository}/tree/{git('describe', '--tags', '--exact-match')}"
            except subprocess.SubprocessError:
                url = f"{repository}/tree/{git('rev-parse', 'HEAD')}"
            pushed = bool(git("branch", "-r", "--contains", "HEAD"))
    except (OSError, subprocess.SubprocessError):  # no Git installed / no Git checkout
        commit = os.environ.get("NETASCORE_COMMIT") or None
        if commit:
            # e.g. 'dev-main, v1.1.1-144-g37365cd-dirty' (commit 37365cd) or 'v2.0.0' (release tag)
            describe = re.sub(r"-dirty$", "", commit.split(", ")[-1])
            match = re.search(r"-g([0-9a-f]{7,40})$", describe)
            url = f"{NETASCORE_REPOSITORY}/tree/{match.group(1) if match else describe}"
    _code_state.update(commit=commit, url=url, pushed=pushed)
    return _code_state


def netascore_commit() -> str:
    """Code state of NetAScore, e.g. 'dev-main, v1.1.1-144-g37365cd' - None if unknown."""
    return _get_code_state()['commit']


def netascore_code_url() -> str:
    """Link to the repository state at the release tag or commit on GitHub - None if unknown."""
    return _get_code_state()['url']


def netascore_code_pushed() -> bool:
    """Whether the commit is on a remote branch (so the URL works)"""
    return _get_code_state()['pushed']


def netascore_version_info() -> str:
    """Version incl. code state, e.g. '2.0.0 (dev-main, v1.1.1-144-g37365cd)' - for log output."""
    commit = netascore_commit()
    return f"{NETASCORE_VERSION} ({commit})" if commit else NETASCORE_VERSION


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
    # SRID stored for the AOI of the case at the start of the run (None: not available)
    stored_aoi_srid = None
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
            h.majorInfo("'on_existing' in section 'database' is no longer used: processing steps always replace their outputs. "
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
