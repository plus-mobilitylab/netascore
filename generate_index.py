import argparse
import os
import sys
import yaml
import re

import toolbox.helper as h
from core.attributes_step import create_attributes_step
from core.db_step import DbStep
from core.export_step import create_exporter
from core.import_step import create_importer, get_stored_aoi_srid
from core.index_step import generate_index, load_profiles
from core.network_step import create_network_step
from core.optional_step import run_optional_importers
from core import metadata
from settings import DbSettings, GlobalSettings, warn_unknown_settings

parser = argparse.ArgumentParser(description='NetAScore: Network Assessment Score Toolbox for Sustainable Mobility')
parser.add_argument('settings_file', type=argparse.FileType('r', encoding='utf-8'),
                    help="""file that contains all settings (input data, referenced mode profiles,...) - runs a demo for Salzburg, Austria if omitted. 
                    More details available in the online documentation at: https://github.com/plus-mobilitylab/netascore""")
parser.add_argument('--skip', nargs='+', choices=['import', 'network', 'optional', 'attributes', 'index', 'export'],
                    help='skip one or more of these steps (in order of execution) - e.g. "--skip import network"')
parser.add_argument('--loglevel', nargs=1, choices=["1", "2", "3", "4"],
                    help="Sets the level of debug outputs on the console: 1=MajorInfo, 2=Info, 3=Detailed, 4=Debug")

args = parser.parse_args()
settings_stream = args.settings_file
skip_steps = args.skip or []
base_path = settings_stream.name.rsplit('/', 1)[0]
if settings_stream.name.find("\\") > 0: # allow use of backslash
    base_path = settings_stream.name.rsplit('\\', 1)[0]
if args.loglevel:
    h.verbose_level = int(args.loglevel[0])
    h.majorInfo(f"using log level {h.verbose_level}")

h.info(f'loading {settings_stream.name}')
h.info(f'skip steps: {str(skip_steps)}')

def require_on_existing_setting(settings: dict):
    if 'on_existing' not in settings:
        h.info('defaulting \'on_existing\' to \'reuse\'')
    settings['on_existing'] = h.normalize_on_existing(settings.get('on_existing'), "section 'import'", default='reuse')


with settings_stream:
    settings: dict = yaml.safe_load(settings_stream)
    h.require_file_version(settings, settings_stream.name, "examples/settings_osm_query.yml")
    warn_unknown_settings(settings)

    # process global settings if given
    if h.has_keys(settings, ['global']):
        global_settings: dict = h.get_section(settings, 'global')
        if h.has_keys(global_settings, ['target_srid']):
            GlobalSettings.custom_srid = h.str_to_numeric(re.sub("[^0-9]", "", str(global_settings['target_srid'])))
            h.info(f"Set the target SRID to {GlobalSettings.get_target_srid()}")
        if h.has_keys(global_settings, ['case_id']):
            GlobalSettings.case_id = re.sub("[^a-zA-Z0-9_]", "", str(global_settings['case_id']))
    
    db_settings: DbSettings = DbSettings.from_dict(settings.get('database'))

    # without a custom target SRID, re-use the SRID determined for the AOI of this case in a previous import
    # (keeps the same CRS for all steps, e.g. when skipping the import step); otherwise the default SRID is used
    if GlobalSettings.custom_srid is None:
        aoi_srid = get_stored_aoi_srid(db_settings)
        if aoi_srid:
            GlobalSettings.default_srid = aoi_srid
            h.info(f"using the target SRID stored for the AOI of case '{GlobalSettings.case_id}': EPSG:{aoi_srid}")

    # check if all required sections are present first before taking any actions
    if 'import' not in skip_steps:
        h.require_keys(settings, ['import'], 'error: section missing:')
    if 'export' not in skip_steps:
        h.require_keys(settings, ['export'], 'error: section missing:')
    profiles = None
    if 'index' not in skip_steps:
        h.require_keys(settings, ['profiles'], 'error: section missing:')
        if not isinstance(settings['profiles'], list) or len(settings['profiles']) == 0:
            h.majorInfo("error: section 'profiles' needs to contain a list of mode profiles (each with 'profile_name' and 'filename').")
            sys.exit(1)
        profiles = load_profiles(base_path, settings['profiles'])

    # record information on this run (exported as metadata to the output)
    metadata.start_run(db_settings, settings, os.path.basename(settings_stream.name), skip_steps)

    # execute processing steps
    if 'import' not in skip_steps:
        h.majorInfo(' === importing ===')
        metadata.start_step('import')
        import_settings: dict = settings['import']
        h.require_keys(import_settings, ['type'], 'error: import section is missing:')
        require_on_existing_setting(import_settings)
        importer: DbStep = create_importer(db_settings, import_settings['type'])
        importer.run_step(import_settings)
        metadata.record_import_file(db_settings, import_settings)
        metadata.complete_step(db_settings, 'import')
    else:
        h.majorInfo(' === skipping import ===')

    if 'network' not in skip_steps and 'import' in settings:
        h.majorInfo(' === running network step ===')
        metadata.start_step('network')
        import_settings: dict = settings['import']
        h.require_keys(import_settings, ['type'], 'error: import section is missing:')
        require_on_existing_setting(import_settings)
        network_step: DbStep = create_network_step(db_settings, import_settings['type'])
        network_step.run_step(import_settings)
        metadata.complete_step(db_settings, 'network')

    # optional import runs after the network step in V2.0 to allow for clipping optional imports 
    # to the spatial extent of the imported network
    if 'optional' not in skip_steps and 'optional' in settings:
        h.majorInfo(' === running optional importers ===')
        metadata.start_step('optional')
        run_optional_importers(db_settings, h.get_section(settings, 'optional'), h.get_section(settings, 'import').get('type'))
        metadata.complete_step(db_settings, 'optional')

    if 'attributes' not in skip_steps and 'import' in settings:
        h.majorInfo(' === running attributes step ===')
        metadata.start_step('attributes')
        import_settings: dict = settings['import']
        h.require_keys(import_settings, ['type'], 'error: import section is missing:')
        require_on_existing_setting(import_settings)
        attributes_step: DbStep = create_attributes_step(db_settings, import_settings['type'])
        attributes_step.run_step(import_settings, settings.get('export'))
        metadata.complete_step(db_settings, 'attributes')

    if 'index' not in skip_steps:
        h.majorInfo(' === generating index ===')
        metadata.start_step('index')
        index_settings: dict = None
        if h.has_keys(settings, ['index']):
            index_settings = settings['index']
        generate_index(db_settings, profiles, index_settings)
        metadata.record_profiles(db_settings, profiles)
        metadata.complete_step(db_settings, 'index')

    if 'export' not in skip_steps:
        h.majorInfo(' === exporting ===')
        metadata.start_step('export')
        export_settings: dict = settings['export']
        h.require_keys(export_settings, ['type'], 'error: export section is missing:')
        exporter: DbStep = create_exporter(db_settings, export_settings['type'])
        exporter.run_step(export_settings)
    else:
        h.majorInfo('skipping export (as listed in skip_steps)')

    metadata.record_run_duration(db_settings)
    metadata.print_run_summary(db_settings)
