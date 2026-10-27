import os
import re
import sqlite3
import subprocess
from datetime import datetime

import toolbox.helper as h
from core import metadata
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings
from toolbox.dbhelper import PostgresConnection


def export_geopackage(connection_string: str, path: str, schema: str, table: str, layer: str, fid: str, geometry_type: str = None, update: bool = False, progress: bool = True, env: dict = None) -> None:
    """Takes in a database table and exports it to a geopackage layer ('env': environment incl. the database password)."""
    # arguments passed as list (no shell): file names may contain any characters
    options = (['-nlt', geometry_type] if geometry_type else []) + (['-update'] if update else []) + (['-progress'] if progress else [])
    subprocess.run(['ogr2ogr', '-f', 'GPKG', path, f'PG:{connection_string}', '-lco', f'FID={fid}', '-lco', 'GEOMETRY_NAME=geom',
                    '-nln', layer, *options, '-sql', f'SELECT * FROM {schema}.{table}'],
        check=True, env=env)


def read_layer_style(style_dir: str, layer: str) -> tuple:
    """Reads the QGIS layer style files of a layer ('<layer>.qml' and optional '<layer>.sld'). Returns (None, None) if
    no QML file exists for the layer."""
    qml_file = os.path.join(style_dir, f'{layer}.qml')
    sld_file = os.path.join(style_dir, f'{layer}.sld')
    if not os.path.exists(qml_file):
        return None, None
    with open(qml_file, encoding='utf-8') as f:
        qml = f.read()
    sld = None
    if os.path.exists(sld_file):
        with open(sld_file, encoding='utf-8') as f:
            sld = f.read()
    return qml, sld


def add_layer_styles(path: str, style_dir: str = os.path.join('resources', 'styles')) -> None:
    """Adds the QGIS layer styles from the style directory ('<layer>.qml', optional '<layer>.sld') to the layers of the
    GeoPackage (table 'layer_styles', as created by QGIS) - each as default style of its layer.
    For the edge layer, one style per mode profile is added, each showing the higher index value of both directions
    (max of 'index_<profile>_ft' and 'index_<profile>_tf') - the style of the first profile is the default style.
    The edge style files refer to the columns 'index_bike_ft' and 'index_bike_tf', which are replaced by the profile's columns."""
    if not os.path.isdir(style_dir):
        h.log(f"no layer styles found ('{style_dir}') - skipping layer styles", h.LOG_LEVEL_2_INFO)
        return
    con = sqlite3.connect(path)
    try:
        # spatial layers of the GeoPackage with their geometry column
        layers = dict(con.execute("SELECT table_name, column_name FROM gpkg_geometry_columns").fetchall())
        # styles to add: (layer, style name, QML, SLD, use as default, description)
        styles = []
        for layer in layers:
            qml, sld = read_layer_style(style_dir, layer)
            if qml is None:
                continue
            if layer != 'edge':
                styles.append((layer, layer, qml, sld, True, f"NetAScore default style of layer '{layer}'"))
                continue
            columns = [row[1] for row in con.execute("PRAGMA table_info(edge)")]
            profiles = [m.group(1) for c in columns if (m := re.fullmatch(r'index_(.+)_ft', c))]
            for i, profile in enumerate(profiles):
                style_qml, style_sld = qml, sld
                for direction in ('ft', 'tf'):
                    style_qml = style_qml.replace(f'index_bike_{direction}', f'index_{profile}_{direction}')
                    style_sld = style_sld.replace(f'index_bike_{direction}', f'index_{profile}_{direction}') if sld else None
                styles.append((layer, f"index_{profile}", style_qml, style_sld, i == 0,
                               f"NetAScore index of profile '{profile}' (higher value of both directions)"))
        if not styles:
            h.log("no layer styles found for the exported layers - skipping layer styles", h.LOG_LEVEL_2_INFO)
            return
        con.execute("""CREATE TABLE IF NOT EXISTS layer_styles (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            f_table_catalog TEXT(256), f_table_schema TEXT(256), f_table_name TEXT(256), f_geometry_column TEXT(256),
            styleName TEXT(30), styleQML TEXT, styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT(30),
            ui TEXT(30), update_time DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
        con.execute("""INSERT OR IGNORE INTO gpkg_contents (table_name, data_type, identifier)
            VALUES ('layer_styles', 'attributes', 'layer_styles')""")
        for layer, name, qml, sld, default, description in styles:
            con.execute("""INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, f_geometry_column,
                styleName, styleQML, styleSLD, useAsDefault, description, owner)
                VALUES ('', '', ?, ?, ?, ?, ?, ?, ?, 'NetAScore')""",
                (layer, layers[layer], name, qml, sld, default, description))
        con.commit()
        h.log(f"added layer styles: {', '.join(f'{s[0]}/{s[1]}' for s in styles)}")
    finally:
        con.close()


class GeopackageExporter(DbStep):
    def run_step(self, settings: dict):
        h.debugLog('exporting geopackage')
        h.log(f"using the following settings: {str(settings)}")

        schema = self.db_settings.entities.network_schema
        directory = GlobalSettings.data_directory

        # open database connection
        h.debugLog('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)

        # set search path
        h.debugLog('set search path')
        db.schema = schema

        filename: str = str(settings.get('filename') or "netascore_<case_id>.gpkg")
        filename = filename.replace("<case_id>", GlobalSettings.case_id)
        filename = filename.replace("<srid>", str(GlobalSettings.get_target_srid()))
        
        # delete file if exists
        if os.path.exists(os.path.join(directory, filename)):
            os.remove(os.path.join(directory, filename))

        # export layers "edge" and "node"
        h.logBeginTask('export layer "edge"')
        export_geopackage(db.connection_string_old, os.path.join(directory, filename), schema, table='export_edge', layer='edge', fid='edge_id', geometry_type='LINESTRING', env=db.tool_env())
        h.logEndTask()

        h.logBeginTask('export layer "node"')
        export_geopackage(db.connection_string_old, os.path.join(directory, filename), schema, table='export_node', layer='node', fid='node_id', geometry_type='POINT', update=True, env=db.tool_env())
        h.logEndTask()

        # export metadata of the run: settings and data sources, input datasets, mode profiles, areas (AOI, clip area, coverage)
        h.logBeginTask('export metadata')
        metadata.record_run_info(self.db_settings, {'output_file': filename, 'target_srid': GlobalSettings.get_target_srid(),
                                               'exported_at': datetime.now().isoformat(timespec='seconds')})
        # the export step is completed with the export of the metadata (time / run duration until here)
        metadata.complete_step(self.db_settings, 'export')
        metadata.record_run_duration(self.db_settings)
        exports = metadata.create_meta_export_tables(db, schema, self.db_settings.entities.data_schema, GlobalSettings.get_target_srid())
        for table, layer, geometry_type in exports:
            export_geopackage(db.connection_string_old, os.path.join(directory, filename), schema, table=table, layer=layer, fid='fid',
                              geometry_type=geometry_type, update=True, progress=False, env=db.tool_env())
        metadata.drop_meta_export_tables(db, schema)
        h.logEndTask()

        # QGIS layer styles (for edge layer: one per mode profile)
        add_layer_styles(os.path.join(directory, filename))

        # close database connection
        h.debugLog('close database connection')
        db.close()


def create_exporter(db_settings: DbSettings, export_type: str):
    if export_type == 'geopackage':
        return GeopackageExporter(db_settings)
    raise NotImplementedError(f"export type '{export_type}' not implemented")
