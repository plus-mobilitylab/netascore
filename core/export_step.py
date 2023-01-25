import os
import subprocess

import toolbox.helper as h
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings
from toolbox.dbhelper import PostgresConnection


def export_geopackage(connection_string: str, path: str, schema: str, table: str, layer: str, fid: str, geometry_type: str = None, update: bool = False) -> None: 
    """Takes in a database table and exports it to a geopackage layer."""
    geometry_type = f"-nlt {geometry_type}" if geometry_type else ""
    update = "-update" if update else ""

    subprocess.run(f"ogr2ogr -f \"GPKG\" \"{path}\" PG:\"{connection_string}\" -lco FID={fid} -lco GEOMETRY_NAME=geom -nln {layer} {geometry_type} {update} -progress -sql \"SELECT * FROM {schema}.{table}\"", 
        shell=True, check=True)


class GeopackageExporter(DbStep):
    def run_step(self, settings: dict):
        h.info('exporting geopackage')
        h.log(f"using the following settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.info('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)

        # set search path
        h.log('set search path')
        db.schema = schema

        filename: str = settings['filename']
        filename = filename.replace("<case_id>", GlobalSettings.case_id)
        filename = filename.replace("<srid>", str(GlobalSettings.get_target_srid()))
        
        # delete file if exists
        if os.path.exists(os.path.join(directory, filename)):
            os.remove(os.path.join(directory, filename))

        # export layers "edge" and "node"
        h.logBeginTask('export layer "edge"')
        export_geopackage(db.connection_string_old, os.path.join(directory, filename), schema, table='export_edge', layer='edge', fid='edge_id', geometry_type='LINESTRING')
        h.logEndTask()

        h.logBeginTask('export layer "node"')
        export_geopackage(db.connection_string_old, os.path.join(directory, filename), schema, table='export_node', layer='node', fid='node_id', geometry_type='POINT', update=True)
        h.logEndTask()

        # close database connection
        h.log('close database connection')
        db.close()


def create_exporter(db_settings: DbSettings, export_type: str):
    if export_type == 'geopackage':
        return GeopackageExporter(db_settings)
    raise NotImplementedError(f"export type '{export_type}' not implemented")
