import os
import re
import shutil
import subprocess
import sys

from osgeo import gdal, ogr

import toolbox.helper as h
from core import dataset_registry as registry
from core import import_step
from core.db_step import DbStep
from settings import DbSettings, GlobalSettings
from toolbox.dbhelper import PostgresConnection

# GDAL/OGR errors raise exceptions (default from GDAL 4.0 on)
gdal.UseExceptions()
ogr.UseExceptions()


def import_raster(connection_string: str, path: str, schema: str, table: str, input_srid: int = 0) -> None:
    if not os.path.exists(path):
        raise Exception(f"The provided input file could not be found. Please check file location and name for '{path}'")
    """Takes in a path to a geotiff raster file and imports it to a database raster table."""
    for tool in ['raster2pgsql', 'psql']:
        if shutil.which(tool) is None:
            raise Exception(f"{tool} (part of PostgreSQL / PostGIS) is required for importing raster data (DEM), but was not found.")
    # raster2pgsql | psql - connected in Python (no shell, works cross-platform); both exit codes are checked
    dump = subprocess.Popen(['raster2pgsql', '-s', str(input_srid), '-I', '-C', '-M', path, '-t', 'auto', f"{schema}.{table}"],
                            stdout=subprocess.PIPE)
    load = subprocess.run(['psql', connection_string, '--variable', 'ON_ERROR_STOP=on', '--quiet'], stdin=dump.stdout)
    dump.stdout.close()
    if dump.wait() != 0 or load.returncode != 0:
        raise Exception(f"Import of raster '{path}' failed (raster2pgsql: exit code {dump.returncode}, psql: exit code {load.returncode}).")


def clip_raster(path_in: str, path_out: str, window: tuple) -> bool:
    """Clips a raster to the given bbox (min x, min y, max x, max y) in the coordinate system of the raster.
    The window is limited to the raster extent (no padding of areas outside). Returns False if the window does not intersect the raster."""
    raster = gdal.Open(path_in)
    gt = raster.GetGeoTransform()
    raster_x = sorted([gt[0], gt[0] + gt[1] * raster.RasterXSize])
    raster_y = sorted([gt[3], gt[3] + gt[5] * raster.RasterYSize])
    raster = None
    min_x, max_x = max(window[0], raster_x[0]), min(window[2], raster_x[1])
    min_y, max_y = max(window[1], raster_y[0]), min(window[3], raster_y[1])
    if min_x >= max_x or min_y >= max_y:
        return False
    subprocess.run(f"gdal_translate -q -projwin {min_x} {max_y} {max_x} {min_y} -co COMPRESS=DEFLATE -co TILED=YES \"{path_in}\" \"{path_out}\"",
        shell=True, check=True)
    return True


class OptionalImporter(DbStep):
    """Base class of optional importers: imports a dataset into the data schema and records it in the dataset registry."""
    # extent of the network incl. margin (min lon, min lat, max lon, max lat) used to filter data on import; None: no filter
    extent: tuple = None
    dataset: str = None                  # name of the dataset (table name)
    tables: list = None                  # tables created by the importer (default: [dataset])

    def run_step(self, settings: dict):
        h.log(f'importing {self.dataset}')
        h.log(f"using settings: {str(settings)}")
        schema = self.db_settings.entities.data_schema
        path = os.path.join(GlobalSettings.data_directory, settings['filename'])
        if not os.path.exists(path):
            raise Exception(f"The provided input file could not be found. Please check file location and name for '{path}'")
        # per-dataset setting 'on_existing' (default: setting of the database section)
        on_existing = h.normalize_on_existing(settings.get('on_existing'), f"optional import '{self.dataset}'", default='reuse')
        layers = self.get_layers(path, settings)
        source = registry.file_signature(path, layers)
        options = self.get_options(settings)

        h.debugLog('open database connection')
        db = PostgresConnection.from_settings_object(self.db_settings)
        db.init_extensions_and_schema(schema)
        h.logBeginTask(f'import {self.dataset}')
        if registry.prepare_import(db, schema, self.dataset, self.tables or [self.dataset], on_existing, source, options, self.extent):
            srid, coverage = self.import_data(db, schema, path, layers, settings)
            if srid is None:  # nothing imported
                registry.remove(db, schema, self.dataset)
            else:
                if settings.get('coverage'):  # area covered by the data, given by the user
                    coverage = registry.coverage_from_file(os.path.join(GlobalSettings.data_directory, settings['coverage']))
                registry.register(db, schema, self.dataset, source, options, srid, self.extent, coverage)
        h.logEndTask()
        h.debugLog('close database connection')
        db.close()

    def get_layers(self, path: str, settings: dict) -> list:
        return None  # all layers

    def get_options(self, settings: dict) -> dict:
        return {}  # import settings that affect the content of the dataset

    def import_data(self, db: PostgresConnection, schema: str, path: str, layers: list, settings: dict) -> tuple:
        """Imports the data. Returns the coordinate system of the stored data and the coverage of the source data (WKT, WGS84)
        - or (None, None) if nothing was imported."""
        raise NotImplementedError()


class VectorImporter(OptionalImporter):
    """Imports vector data (GeoPackage) for the network extent, transformed to the target coordinate system."""
    geometry_types: list = None

    def import_data(self, db: PostgresConnection, schema: str, path: str, layers: list, settings: dict) -> tuple:
        table = (self.tables or [self.dataset])[0]
        import_step.import_geopackage(db.connection_string_old, path, schema, table=table, layers=layers,
            target_srid=GlobalSettings.get_target_srid(), geometry_types=self.geometry_types, extent=self.extent)
        return GlobalSettings.get_target_srid(), registry.vector_coverage(path, layers)


class DemImporter(OptionalImporter):
    dataset = 'dem'

    def get_options(self, settings: dict) -> dict:
        return {'srid': self._dem_srid(settings)}

    def _dem_srid(self, settings: dict) -> int:
        return int(re.sub(r"[^0-9]", "", str(settings['srid'])))

    def import_data(self, db: PostgresConnection, schema: str, path: str, layers: list, settings: dict) -> tuple:
        dem_srid = self._dem_srid(settings)
        coverage = registry.raster_coverage(path, dem_srid)
        clipped_path = None
        if self.extent:
            # only import the part of the DEM within the network extent (transformed to the coordinate system of the DEM)
            window = db.query_one("""
                WITH e AS (SELECT ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), %s) AS geom)
                SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) FROM e;""", (*self.extent, dem_srid))
            clipped_path = os.path.join(GlobalSettings.data_directory, f"dem_{GlobalSettings.case_id}_clip.tif")
            h.log(f"clipping DEM to the network extent: {window} (EPSG:{dem_srid})")
            if not clip_raster(path, clipped_path, window):
                h.majorInfo(f"WARNING: the DEM '{settings['filename']}' does not overlap the network extent - DEM is not imported, gradients cannot be computed.")
                return None, None
            path = clipped_path
        # raster is imported without reprojection - during the attributes step, the network will be temporarily reprojected to DEM srid.
        import_raster(db.connection_string, path, schema, table='dem', input_srid=dem_srid)  # 4 m 34 s
        #if clipped_path:
        #    os.remove(clipped_path)
        return dem_srid, coverage


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


class NoiseImporter(VectorImporter):
    dataset = 'noise'
    tables = ['noise_import', 'noise']
    geometry_types = ['POLYGON', 'MULTIPOLYGON']

    def get_layers(self, path: str, settings: dict) -> list:
        return [get_noise_layer(path, settings)]

    def get_options(self, settings: dict) -> dict:
        return {'column_noise': settings.get('column_noise') or 'noise', 'value_mapping': settings.get('value_mapping')}

    def import_data(self, db: PostgresConnection, schema: str, path: str, layers: list, settings: dict) -> tuple:
        result = super().import_data(db, schema, path, layers, settings)
        # column with noise values (optional setting 'column_noise', default: 'noise');
        # column names are converted to lower case and special characters are replaced by '_' during import (ogr2ogr)
        column_noise = str(settings.get('column_noise') or 'noise')
        rows = db.query_all("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = 'noise_import';", (schema,))
        available = [r[0] for r in rows if r[0] not in ('fid', 'import_fid', 'geom')]
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
        h.log('postprocess noise')
        db.execute(f"""
            DROP TABLE IF EXISTS noise;
            CREATE TABLE noise AS(
                SELECT row_number() over() as id, ST_Subdivide(n.geom, 200) as geom, {noise_expr} AS noise
                FROM noise_import n
            );
            CREATE INDEX noise_geom_idx ON noise USING gist (geom);
        """, params or None)
        db.commit()
        return result


class BuildingImporter(VectorImporter):
    dataset = 'building'
    geometry_types = ['POLYGON']


class CrossingImporter(VectorImporter):
    dataset = 'crossing'
    geometry_types = ['POINT', 'LINESTRING']


class FacilityImporter(VectorImporter):
    dataset = 'facility'
    geometry_types = ['POINT', 'POLYGON']


class GreennessImporter(VectorImporter):
    dataset = 'greenness'
    geometry_types = ['POLYGON']


class WaterImporter(VectorImporter):
    dataset = 'water'
    geometry_types = ['LINESTRING', 'POLYGON']


class ParkingImporter(VectorImporter):
    dataset = 'parking'
    geometry_types = ['LINESTRING', 'POLYGON']


class SightsImporter(VectorImporter):
    dataset = 'sights'
    geometry_types = ['POINT', 'POLYGON']


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


def get_network_extent(db_settings: DbSettings, margin: float = 50) -> tuple:
    """Returns the extent of the network (min lon, min lat, max lon, max lat), extended by a margin (in m) to include
    nearby features (relevant for search radii of attributes: up to 30 m). Returns None if no network exists yet."""
    db = PostgresConnection.from_settings_object(db_settings)
    network_table = f"{db_settings.entities.network_schema}.network_edge"
    try:
        if not db.query_one("SELECT to_regclass(%s) IS NOT NULL;", (network_table,))[0]:
            return None
        extent = db.query_one(f"""
            WITH e AS (SELECT ST_Transform(ST_Expand(ST_SetSRID(ST_Extent(geom)::geometry, max(ST_SRID(geom))), %s), 4326) AS geom
                       FROM {network_table})
            SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) FROM e WHERE geom IS NOT NULL;""", (margin,))
        return tuple(extent) if extent else None
    finally:
        db.close()


def run_optional_importers(db_settings: DbSettings, optional_importer_settings: dict, network_type: str = None):
    # vector data is only imported for the extent of the network (incl. margin)
    extent = get_network_extent(db_settings)
    if extent:
        h.info(f"optional data is imported for the network extent (incl. 50 m margin)")
    else:
        h.info("no network found - optional data is imported without spatial filter")
    # subsection 'defaults': provides defaults for all optional imports (can be overridden per dataset)
    defaults = h.get_section(optional_importer_settings, 'defaults')
    default_on_existing = h.normalize_on_existing(defaults.get('on_existing'), "section 'optional' > 'defaults'", default='reuse')
    default_clip = str(defaults.get('clip') or 'network').strip().lower()
    for import_type, settings in optional_importer_settings.items():
        if import_type == 'defaults':
            continue
        if import_type == 'dem' and str(network_type).lower() in ('gip', 'gip2'):
            h.majorInfo("NOTE: the DEM is not imported - for GIP, gradients are computed from the elevation data contained in the GIP dataset.")
            continue
        if import_type == 'osm':
            # optional OSM import (for GIP): OSM files only
            h.require_keys(settings, ['filename'], "error: the optional OSM import requires an OSM file, e.g. an extract from "
                           "https://download.geofabrik.de - it is clipped to the extent of the network (unless 'clip: none' is set).")
        else:
            required = ['filename', 'srid'] if import_type == 'dem' else ['filename']
            h.require_keys(settings, required, f"error: optional importer '{import_type}' needs the following keys: {', '.join(required)}")
        settings = dict(settings)
        if not settings.get('on_existing'):
            settings['on_existing'] = default_on_existing
        # setting 'clip': 'network' (default) - only import data within the network extent; 'none' - import the whole file
        clip = str(settings.get('clip') or default_clip).strip().lower()
        if clip not in ['network', 'none']:
            h.majorInfo(f"error: invalid value '{clip}' for setting 'clip' of optional importer '{import_type}'. Allowed values: [network/none]")
            sys.exit(1)
        if clip == 'none' and extent:
            h.info(f"optional importer '{import_type}': clipping disabled - importing the whole file")
        optional_importer = create_optional_importer(db_settings, import_type)
        if import_type == 'osm':
            optional_importer.optional = True
            optional_importer.network_extent = extent if clip == 'network' else None
        else:
            optional_importer.extent = extent if clip == 'network' else None
        optional_importer.run_step(settings)
