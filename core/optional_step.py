import os
import subprocess

import toolbox.helper as h
from core import import_step
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings
from toolbox.dbhelper import PostgresConnection


def import_raster(connection_string: str, path: str, schema: str, table: str, input_srid: int = 0) -> None:
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
        if db.handle_conflicting_output_tables(['noise'], schema):
            import_step.import_geopackage(db.connection_string_old, os.path.join(directory, settings['filename']), schema, 
                table='noise', target_srid=GlobalSettings.get_target_srid(), geometry_types=['POLYGON', 'MULTIPOLYGON'])
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
    raise NotImplementedError(f"import type '{import_type}' not implemented")


def run_optional_importers(db_settings: DbSettings, optional_importer_settings: dict):
    for import_type, settings in optional_importer_settings.items():
        optional_importer = create_optional_importer(db_settings, import_type)
        optional_importer.run_step(settings)
