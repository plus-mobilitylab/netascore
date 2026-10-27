-- osm2pgsql flex output configuration for the NetAScore OSM import (requires osm2pgsql >= 1.9).
--
-- Tables (WGS84, EPSG:4326):
-- - osm_point, osm_line, osm_polygon: OSM objects with the tags listed below as columns, all other tags in the
--   hstore column 'tags' (same structure as the former pgsql output with --latlong --hstore and its default style)
-- - osm_bicycle_route: member ways of bicycle route relations with network level and direction (indicator
--   'designated_route')
--
-- All tagged objects are imported (not only those NetAScore currently uses), so further datasets can be derived from
-- the OSM tables with SQL only.
--
-- Partly based on 'flex-config/compatible.lua' of osm2pgsql (released into the Public Domain).

local srid = 4326
local prefix = 'osm'

-- long linestrings are split into parts of max. 1 degree (as with the pgsql output)
local max_length = 1

-- ways with any of the following keys are treated as polygon (if closed and not tagged 'area=no')
local polygon_keys = {
    'aeroway', 'amenity', 'building', 'harbour', 'historic', 'landuse', 'leisure', 'man_made', 'military', 'natural',
    'office', 'place', 'power', 'public_transport', 'shop', 'sport', 'tourism', 'water', 'waterway', 'wetland',
    'abandoned:aeroway', 'abandoned:amenity', 'abandoned:building', 'abandoned:landuse', 'abandoned:power',
    'area:highway'
}

-- the following keys are deleted
local delete_keys = {
    'attribution', 'comment', 'created_by', 'fixme', 'note', 'note:*', 'odbl', 'odbl:note', 'source', 'source:*',
    'source_ref', 'way', 'way_area', 'z_order'
}

-- tags stored in separate columns (all other tags: hstore column 'tags')
local point_columns = {
    'access', 'addr:housename', 'addr:housenumber', 'addr:interpolation', 'admin_level', 'aerialway', 'aeroway',
    'amenity', 'area', 'barrier', 'bicycle', 'brand', 'bridge', 'boundary', 'building', 'capital', 'construction',
    'covered', 'culvert', 'cutting', 'denomination', 'disused', 'ele', 'embankment', 'foot', 'generator:source',
    'harbour', 'highway', 'historic', 'horse', 'intermittent', 'junction', 'landuse', 'layer', 'leisure', 'lock',
    'man_made', 'military', 'motorcar', 'name', 'natural', 'office', 'oneway', 'operator', 'place', 'population',
    'power', 'power_source', 'public_transport', 'railway', 'ref', 'religion', 'route', 'service', 'shop', 'sport',
    'surface', 'toll', 'tourism', 'tower:type', 'tunnel', 'water', 'waterway', 'wetland', 'width', 'wood'
}

local non_point_columns = {
    'access', 'addr:housename', 'addr:housenumber', 'addr:interpolation', 'admin_level', 'aerialway', 'aeroway',
    'amenity', 'area', 'barrier', 'bicycle', 'brand', 'bridge', 'boundary', 'building', 'construction', 'covered',
    'culvert', 'cutting', 'denomination', 'disused', 'embankment', 'foot', 'generator:source', 'harbour', 'highway',
    'historic', 'horse', 'intermittent', 'junction', 'landuse', 'layer', 'leisure', 'lock', 'man_made', 'military',
    'motorcar', 'name', 'natural', 'office', 'oneway', 'operator', 'place', 'population', 'power', 'power_source',
    'public_transport', 'railway', 'ref', 'religion', 'route', 'service', 'shop', 'sport', 'surface', 'toll',
    'tourism', 'tower:type', 'tracktype', 'tunnel', 'water', 'waterway', 'wetland', 'width', 'wood'
}

-- network level of bicycle routes (tag 'network' of the route relation; other values: 'unknown')
local route_levels = {
    icn = 'international',
    ncn = 'national',
    rcn = 'regional',
    regional = 'regional',
    lcn = 'local'
}

-- ---------------------------------------------------------------------------------------------------------------------

local function gen_columns(text_columns, area, geometry_type)
    local columns = {}
    for _, c in ipairs(text_columns) do
        columns[#columns + 1] = { column = c, type = 'text' }
    end
    columns[#columns + 1] = { column = 'z_order', type = 'int' }
    if area then
        columns[#columns + 1] = { column = 'way_area', type = 'real' }
    end
    columns[#columns + 1] = { column = 'tags', type = 'hstore' }
    columns[#columns + 1] = { column = 'way', type = geometry_type, projection = srid, not_null = true }
    return columns
end

local tables = {}

tables.point = osm2pgsql.define_table{
    name = prefix .. '_point',
    ids = { type = 'node', id_column = 'osm_id' },
    columns = gen_columns(point_columns, false, 'point')
}

tables.line = osm2pgsql.define_table{
    name = prefix .. '_line',
    ids = { type = 'way', id_column = 'osm_id' },
    columns = gen_columns(non_point_columns, true, 'linestring')
}

tables.polygon = osm2pgsql.define_table{
    name = prefix .. '_polygon',
    ids = { type = 'area', id_column = 'osm_id' },
    columns = gen_columns(non_point_columns, true, 'geometry')
}

-- one row per bicycle route relation and member way; direction: 'both' or - for members with role 'forward' /
-- 'backward' - only in ('forward') or against ('backward') the direction of the way
tables.bicycle_route = osm2pgsql.define_table{
    name = prefix .. '_bicycle_route',
    ids = { type = 'relation', id_column = 'relation_id' },
    columns = {
        { column = 'way_id', type = 'int8', not_null = true },
        { column = 'route_level', type = 'text', not_null = true },
        { column = 'direction', type = 'text', not_null = true },
        { column = 'network', type = 'text' },
        { column = 'name', type = 'text' },
        { column = 'ref', type = 'text' }
    },
    indexes = {
        { column = 'way_id', method = 'btree' }
    }
}

-- ---------------------------------------------------------------------------------------------------------------------

local z_order_lookup = {
    proposed = 1, construction = 2, steps = 10, cycleway = 10, bridleway = 10, footway = 10, path = 10, track = 11,
    service = 15, tertiary_link = 24, secondary_link = 25, primary_link = 27, trunk_link = 28, motorway_link = 29,
    raceway = 30, pedestrian = 31, living_street = 32, road = 33, unclassified = 33, residential = 33, tertiary = 34,
    secondary = 36, primary = 37, trunk = 38, motorway = 39
}

local function as_bool(value)
    return value == 'yes' or value == 'true' or value == '1'
end

local function get_z_order(tags)
    local z_order = 100 * math.floor(tonumber(tags.layer or '0') or 0)
    if tags.highway then
        z_order = z_order + (z_order_lookup[tags.highway] or 0)
    end
    if tags.railway then
        z_order = z_order + 35
    end
    if as_bool(tags.bridge) then
        z_order = z_order + 100
    end
    if as_bool(tags.tunnel) then
        z_order = z_order - 100
    end
    return z_order
end

local function make_check_in_list_func(list)
    local h = {}
    for _, k in ipairs(list) do
        h[k] = true
    end
    return function(tags)
        for k, _ in pairs(tags) do
            if h[k] then
                return true
            end
        end
        return false
    end
end

local is_polygon = make_check_in_list_func(polygon_keys)
local clean_tags = osm2pgsql.make_clean_tags_func(delete_keys)

-- splits the tags into columns and the hstore column 'tags'
local function make_get_output(columns)
    local h = {}
    for _, k in ipairs(columns) do
        h[k] = true
    end
    return function(tags)
        local output = { tags = {} }
        for k, v in pairs(tags) do
            if h[k] then
                output[k] = v
            else
                output.tags[k] = v
            end
        end
        return output
    end
end

local get_point_output = make_get_output(point_columns)
local get_non_point_output = make_get_output(non_point_columns)

-- inserts each polygon of a multipolygon as separate row (as with the pgsql output)
local function insert_polygons(output, geom)
    for sgeom in geom:geometries() do
        output.way = sgeom
        output.way_area = sgeom:area()
        tables.polygon:insert(output)
    end
end

-- ---------------------------------------------------------------------------------------------------------------------

function osm2pgsql.process_node(object)
    if clean_tags(object.tags) then
        return
    end
    local output = get_point_output(object.tags)
    output.way = object:as_point()
    tables.point:insert(output)
end

function osm2pgsql.process_way(object)
    if clean_tags(object.tags) then
        return
    end

    local polygon
    local area_tag = object.tags.area
    if area_tag == 'yes' or area_tag == '1' or area_tag == 'true' then
        polygon = true
    elseif area_tag == 'no' or area_tag == '0' or area_tag == 'false' then
        polygon = false
    else
        polygon = is_polygon(object.tags)
    end
    polygon = polygon and object.is_closed

    local output = get_non_point_output(object.tags)
    output.z_order = get_z_order(object.tags)

    if polygon then
        local geom = object:as_polygon()
        output.way = geom
        output.way_area = geom:area()
        tables.polygon:insert(output)
    else
        for sgeom in object:as_linestring():segmentize(max_length):geometries() do
            output.way = sgeom
            tables.line:insert(output)
        end
    end
end

local function process_bicycle_route(object)
    -- proposed routes are not (yet) signposted
    if object.tags.state == 'proposed' then
        return
    end
    local route_level = route_levels[object.tags.network] or 'unknown'
    for _, member in ipairs(object.members) do
        if member.type == 'w' then
            local direction = 'both'
            if member.role == 'forward' or member.role == 'backward' then
                direction = member.role
            end
            tables.bicycle_route:insert{
                way_id = member.ref,
                route_level = route_level,
                direction = direction,
                network = object.tags.network,
                name = object.tags.name,
                ref = object.tags.ref
            }
        end
    end
end

function osm2pgsql.process_relation(object)
    local rtype = object.tags.type
    if rtype == 'route' and object.tags.route == 'bicycle' then
        process_bicycle_route(object)
        return
    end

    if clean_tags(object.tags) then
        return
    end
    rtype = object:grab_tag('type')
    -- relations without further tags are skipped
    if (rtype ~= 'multipolygon' and rtype ~= 'boundary') or not next(object.tags) then
        return
    end

    local output = get_non_point_output(object.tags)
    output.z_order = get_z_order(object.tags)
    insert_polygons(output, object:as_multipolygon())
end
