CREATE OR REPLACE FUNCTION delete_dangling_edges()
RETURNS void AS $$
DECLARE
    count integer;
BEGIN
    count := 0;

    DROP TABLE IF EXISTS dangling_edges;
    CREATE TABLE dangling_edges AS (
        WITH points_cnt AS ( -- 777, 184, 88, 42, 18, 8, 1
            SELECT geom, count(*)
            FROM indoor_points
            GROUP BY geom
        ),
        indoor_links AS (
            SELECT id AS link_id, geom
            FROM network_corrected
            WHERE tags -> 'indoor' = 'yes'
        ),
        intersections_links AS (
            SELECT a.link_id
            FROM indoor_links a
                JOIN points_cnt b ON (ST_Intersects(a.geom, b.geom))
            WHERE b.count > 1
        ),
        intersections_counts AS (
            SELECT link_id, count(*) AS cnt
            FROM intersections_links
            GROUP BY link_id
        )
        SELECT link_id
        FROM intersections_counts
        WHERE cnt < 2
    );

    count := (SELECT count(link_id) FROM dangling_edges);
    RAISE NOTICE 'dangling edges: %', count;

    WHILE count > 0 LOOP
        DELETE FROM indoor_points WHERE link_id IN (SELECT link_id FROM dangling_edges);
        DELETE FROM network_corrected WHERE id IN (SELECT link_id FROM dangling_edges);

        DROP TABLE IF EXISTS dangling_edges;
        CREATE TABLE dangling_edges AS (
            WITH points_cnt AS (
                SELECT geom, count(*)
                FROM indoor_points
                GROUP BY geom
            ),
            indoor_links AS (
                SELECT id AS link_id, geom
                FROM network_corrected
                WHERE tags -> 'indoor' = 'yes'
            ),
            intersections_links AS (
                SELECT a.link_id
                FROM indoor_links a
                    JOIN points_cnt b ON (ST_Intersects(a.geom, b.geom))
                WHERE b.count > 1
            ),
            intersections_counts AS (
                SELECT link_id, count(*) AS cnt
                FROM intersections_links
                GROUP BY link_id
            )
            SELECT link_id
            FROM intersections_counts
            WHERE cnt < 2
        );

        count := (SELECT count(link_id) FROM dangling_edges);
        RAISE NOTICE 'dangling edges: %', count;
    END LOOP;

    DROP TABLE IF EXISTS dangling_edges;
END
$$ LANGUAGE plpgsql;