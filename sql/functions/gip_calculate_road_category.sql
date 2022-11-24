CREATE OR REPLACE FUNCTION calculate_road_category(
    access_tow_car boolean, access_bkw_car boolean,
    access_tow_bike boolean, access_bkw_bike boolean,
    funcroadclass integer, streetcat varchar, basetype varchar,
    bikefeaturetow varchar, bikefeaturebkw varchar
)
RETURNS varchar AS $$
DECLARE
    basetype_array       varchar[];
    bikefeaturetow_array varchar[];
    bikefeaturebkw_array varchar[];
    indicator_values     integer[];
    indicator_value      varchar;
BEGIN
    basetype_array := string_to_array(basetype, ';');
    bikefeaturetow_array := string_to_array(bikefeaturetow, ';');
    bikefeaturebkw_array := string_to_array(bikefeaturebkw, ';');

    IF basetype_array IS NOT NULL THEN
        FOR i IN 1..array_length(basetype_array, 1) LOOP
            IF streetcat = 'B' THEN
                indicator_values := array_append(indicator_values, 1);
            ELSEIF (streetcat = 'L' OR funcroadclass = 2) AND streetcat <> 'B' THEN
                indicator_values := array_append(indicator_values, 2);
            ELSEIF ((streetcat = 'G' AND funcroadclass >= 3) OR
                    (streetcat = 'R' AND funcroadclass BETWEEN 3 AND 5) OR
                    (streetcat NOT IN ('B', 'L') AND funcroadclass BETWEEN 3 AND 5)) AND
                   (bikefeaturetow_array[i] <> 'VK_BE' AND bikefeaturebkw_array[i] <> 'VK_BE' AND
                    bikefeaturetow_array[i] <> 'FRS' AND bikefeaturebkw_array[i] <> 'FRS') AND
                   (access_tow_car OR access_bkw_car) THEN
                indicator_values := array_append(indicator_values, 3);
            ELSEIF streetcat NOT IN ('B', 'L', 'G') AND funcroadclass > 5 AND
                   (bikefeaturetow_array[i] <> 'VK_BE' AND bikefeaturebkw_array[i] <> 'VK_BE' AND
                    bikefeaturetow_array[i] <> 'FRS' AND bikefeaturebkw_array[i] <> 'FRS') AND
                   (access_tow_car OR access_bkw_car) THEN
                indicator_values := array_append(indicator_values, 4);
            ELSEIF (bikefeaturetow_array[i] = 'VK_BE' OR bikefeaturebkw_array[i] = 'VK_BE' OR
                    bikefeaturetow_array[i] = 'FRS' OR bikefeaturebkw_array[i] = 'FRS') AND
                   (access_tow_car OR access_bkw_car) THEN
                indicator_values := array_append(indicator_values, 5);
            ELSEIF (bikefeaturetow_array[i] = 'FUZO' OR bikefeaturebkw_array[i] = 'FUZO') OR
                   ((access_tow_car IS FALSE AND access_bkw_car IS FALSE) AND (access_tow_bike OR access_bkw_bike) AND
                    basetype_array[i] <> '7') THEN
                indicator_values := array_append(indicator_values, 6);
            ELSEIF (access_tow_bike IS FALSE AND access_bkw_bike IS FALSE) OR basetype_array[i] = '7' THEN
                indicator_values := array_append(indicator_values, 7);
            END IF;
        END LOOP;

        indicator_value :=
            CASE
                WHEN '1' = ANY (indicator_values) THEN 'primary'
                WHEN '2' = ANY (indicator_values) THEN 'secondary'
                WHEN '3' = ANY (indicator_values) THEN 'residential'
                WHEN '4' = ANY (indicator_values) THEN 'service'
                WHEN '5' = ANY (indicator_values) THEN 'calmed'
                WHEN '6' = ANY (indicator_values) THEN 'no_mit'
                WHEN '7' = ANY (indicator_values) THEN 'path'
            END;
    END IF;

    RETURN indicator_value;
END;
$$ LANGUAGE plpgsql;