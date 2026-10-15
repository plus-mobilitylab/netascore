import os
import re
import subprocess
import sys

from osgeo import ogr

import toolbox.helper as h
from core import import_step
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings
from toolbox.dbhelper import PostgresConnection


def import_raster(connection_string: str, path: str, schema: str, table: str, input_srid: int = 0) -> None:
    if not os.path.exists(path):
        raise Exception(f"The provided input file could not be found. Please check file location and name for '{path}'")
    """Takes in a path to a geotiff raster file and imports it to a database raster table."""
    subprocess.run(f"raster2pgsql -s {input_srid} -I -C -M \"{path}\" -t auto {schema}.{table} | psql \"{connection_string}\" --variable ON_ERROR_STOP=on --quiet", 
        shell=True, check=True)


class DemImporter(DbStep):
    def run_step(self, settings: dict):
        h.info('importing dem:')
        h.log(f"using settings: {str(settings)}")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)

        # import DEM
        h.logBeginTask('import dem raster')
        if db.handle_conflicting_output_tables(['dem'], schema):
            # raster is imported without reprojection - during the attributes step, the network will be temporarily reprojected to DEM srid.
            import_raster(db.connection_string, os.path.join(directory, settings['filename']), schema, table='dem', input_srid=settings['srid'])  # 4 m 34 s
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()


def get_noise_layer(path: str, settings: dict) -> str:
    """Returns the layer to import from the noise dataset: either using the setting 'layer', or the only geometry layer available.
    In case of multiple noise layers one must be specified via the 'layer' setting."""
    if not os.path.exists(path):
        raise Exception(f"The provided input file could not be found. Please check file location and name for '{path}'")
    data_source = ogr.Open(path)
    layers = [layer.GetName() for layer in data_source if layer.GetGeomType() != ogr.wkbNone]
    layer = settings.get('layer')
    if layer:
        if str(layer) not in layers:
            h.majorInfo(f"error: noise layer '{layer}' not found in '{path}'. Available layers: {', '.join(layers)}")
            sys.exit(1)
        return str(layer)
    if len(layers) != 1:
        h.majorInfo(f"error: '{path}' contains {len(layers)} layers with geometry. Please specify the noise layer to import "
                    f"using the setting 'layer' in the noise import settings. Available layers: {', '.join(layers)}")
        sys.exit(1)
    return layers[0]


class NoiseImporter(DbStep):
    def run_step(self, settings: dict):
        h.log('importing noise:')
        h.log(f"using settings: {str(settings)}")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)

        # import noise
        h.logBeginTask('import noise')
        if db.handle_conflicting_output_tables(['noise', 'noise_import'], schema):
            path = os.path.join(directory, settings['filename'])
            import_step.import_geopackage(db.connection_string_old, path, schema, table='noise_import', layers=[get_noise_layer(path, settings)],
                target_srid=GlobalSettings.get_target_srid(), geometry_types=['POLYGON', 'MULTIPOLYGON'])
        h.logEndTask()
        # column with noise values (optional setting 'column_noise', default: 'noise');
        # column names are converted to lower case and special characters are replaced by '_' during import (ogr2ogr)
        column_noise = str(settings.get('column_noise') or 'noise')
        rows = db.query_all("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = 'noise_import';", (schema,))
        available = [r[0] for r in rows if r[0] not in ('fid', 'geom')]
        candidates = [column_noise, column_noise.lower(), re.sub(r"[^a-z0-9_]", "_", column_noise.lower())]
        column = next((c for c in candidates if c in available), None)
        if column is None:
            h.majorInfo(f"error: noise column '{column_noise}' not found in '{settings['filename']}'. "
                        f"Please set 'column_noise' in the optional noise settings. Available columns: {', '.join(available)}")
            sys.exit(1)
        # optional mapping of (non-numeric) input values to numeric noise values (setting 'value_mapping'),
        # otherwise the values of the noise column are used as numbers
        value_mapping = settings.get('value_mapping')
        params = []
        if value_mapping:
            if not isinstance(value_mapping, dict) or not all(type(v) in (int, float) for v in value_mapping.values()):
                h.majorInfo(f"error: 'value_mapping' in the optional noise settings needs to map input values to numeric noise values, "
                            f"e.g. {{'55-59': 57, '60-64': 62}}. Found: {value_mapping}")
                sys.exit(1)
            noise_expr = "CASE trim(n.\"" + column + "\"::text) " + " ".join(["WHEN %s THEN %s"] * len(value_mapping)) + " END::numeric"
            for k, v in value_mapping.items():
                params += [str(k).strip(), v]
            # report input values without mapping (these get no noise value)
            unmapped = db.query_all(f"""SELECT DISTINCT trim(n."{column}"::text) FROM noise_import n
                                        WHERE n."{column}" IS NOT NULL AND NOT trim(n."{column}"::text) = ANY(%s) LIMIT 10;""",
                                    ([str(k).strip() for k in value_mapping],))
            if unmapped:
                h.majorInfo(f"WARNING: noise values without entry in 'value_mapping' are treated as areas without noise data, e.g.: {', '.join(r[0] for r in unmapped)}")
        else:
            noise_expr = f'n."{column}"::numeric'
        # split (subdivide) noise polygons to enable spatial indexing
        h.logBeginTask('postprocess noise')
        db.execute(f"""
            DROP TABLE IF EXISTS noise;
            CREATE TABLE noise AS(
                SELECT row_number() over() as id, ST_Subdivide(n.geom, 200) as geom, {noise_expr} AS noise
                FROM noise_import n
            );
            CREATE INDEX noise_geom_idx ON noise USING gist (geom);
        """, params or None)
        db.commit()
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()


class BuildingImporter(DbStep):
    def run_step(self, settings: dict):
        h.info('importing building')
        h.log(f"using settings: {str(settings)}")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)

        # import building
        h.logBeginTask('import building')
        if db.handle_conflicting_output_tables(['building'], schema):
            import_step.import_geopackage(db.connection_string_old, os.path.join(directory, settings['filename']), schema, 
                table='building', target_srid=GlobalSettings.get_target_srid(), geometry_types=['POLYGON'])
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()


class CrossingImporter(DbStep):
    def run_step(self, settings: dict):
        h.log('importing crossing:')
        h.log(f"using settings: {str(settings)}")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)

        # import crossing
        h.logBeginTask('import crossing')
        if db.handle_conflicting_output_tables(['crossing'], schema):
            import_step.import_geopackage(db.connection_string_old, os.path.join(directory, settings['filename']), schema, 
                table='crossing', target_srid=GlobalSettings.get_target_srid(), geometry_types=['POINT', 'LINESTRING'])
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()


class FacilityImporter(DbStep):
    def run_step(self, settings: dict):
        h.log('importing facility:')
        h.log(f"using settings: {str(settings)}")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)

        # import facility
        h.logBeginTask('import facility')
        if db.handle_conflicting_output_tables(['facility'], schema):
            import_step.import_geopackage(db.connection_string_old, os.path.join(directory, settings['filename']), schema, 
                table='facility', target_srid=GlobalSettings.get_target_srid(), geometry_types=['POINT', 'POLYGON'])
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()


class GreennessImporter(DbStep):
    def run_step(self, settings: dict):
        h.log('importing greenness:')
        h.log(f"using settings: {str(settings)}")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)

        # import greenness
        h.logBeginTask('import greenness')
        if db.handle_conflicting_output_tables(['greenness'], schema):
            import_step.import_geopackage(db.connection_string_old, os.path.join(directory, settings['filename']), schema, 
                table='greenness', target_srid=GlobalSettings.get_target_srid(), geometry_types=['POLYGON'])
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()


class WaterImporter(DbStep):
    def run_step(self, settings: dict):
        h.log('importing water:')
        h.log(f"using settings: {str(settings)}")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)

        # import water
        h.logBeginTask('import water')
        if db.handle_conflicting_output_tables(['water'], schema):
            import_step.import_geopackage(db.connection_string_old, os.path.join(directory, settings['filename']), schema, 
                table='water', target_srid=GlobalSettings.get_target_srid(), geometry_types=['LINESTRING', 'POLYGON'])
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()

class ParkingImporter(DbStep):
    def run_step(self, settings: dict):
        h.log('importing parking:')
        h.log(f"using settings: {str(settings)}")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)

        # import tourism
        h.logBeginTask('import parking')
        if db.handle_conflicting_output_tables(['parking'], schema):
            import_step.import_geopackage(db.connection_string_old, os.path.join(directory, settings['filename']), schema,
                table='parking', target_srid=GlobalSettings.get_target_srid(), geometry_types=['LINESTRING', 'POLYGON'])
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()

class SightsImporter(DbStep):
    def run_step(self, settings: dict):
        h.log('importing sights:')
        h.log(f"using settings: {str(settings)}")

        schema = self.db_settings.entities.data_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)

        # import sights
        h.logBeginTask('import sights')
        if db.handle_conflicting_output_tables(['sights'], schema):
            import_step.import_geopackage(db.connection_string_old, os.path.join(directory, settings['filename']), schema,
                table='sights', target_srid=GlobalSettings.get_target_srid(), geometry_types=['POINT', 'POLYGON'])
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()


def create_optional_importer(db_settings: DbSettings, import_type: str):
    if import_type == 'dem':
        return DemImporter(db_settings)
    if import_type == 'noise':
        return NoiseImporter(db_settings)
    if import_type == 'osm':
        return import_step.OsmImporter(db_settings)
    if import_type == 'building':
        return BuildingImporter(db_settings)
    if import_type == 'crossing':
        return CrossingImporter(db_settings)
    if import_type == 'facility':
        return FacilityImporter(db_settings)
    if import_type == 'greenness':
        return GreennessImporter(db_settings)
    if import_type == 'water':
        return WaterImporter(db_settings)
    if import_type == 'parking':
        return ParkingImporter(db_settings)
    if import_type == 'sights':
        return SightsImporter(db_settings)
    raise NotImplementedError(f"optional import type '{import_type}' not implemented. "
                              "Available types: dem, noise, osm, building, crossing, facility, greenness, water, parking, sights")


def run_optional_importers(db_settings: DbSettings, optional_importer_settings: dict):
    for import_type, settings in optional_importer_settings.items():
        required = ['filename', 'srid'] if import_type == 'dem' else ['filename']
        h.require_keys(settings, required, f"error: optional importer '{import_type}' needs the following keys: {', '.join(required)}")
        optional_importer = create_optional_importer(db_settings, import_type)
        optional_importer.run_step(settings)
