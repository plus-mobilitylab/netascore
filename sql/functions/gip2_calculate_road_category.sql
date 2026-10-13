CREATE OR REPLACE FUNCTION calculate_gip2_road_category(
    access_car_ft boolean, access_car_tf boolean,
    access_bicycle_ft boolean, access_bicycle_tf boolean,
    functional_class integer, edge_category varchar, lup_base_type varchar,
    bh_bike_feature_tow varchar, bh_bike_feature_bkw varchar
)
RETURNS varchar AS $$
DECLARE
    lup_base_type_array        varchar[];
    bh_bike_feature_tow_array varchar[];
    bh_bike_feature_bkw_array varchar[];
    indicator_values       integer[];
    indicator_value        varchar;
BEGIN
    lup_base_type_array := string_to_array(lup_base_type, ';');
    bh_bike_feature_tow_array := string_to_array(bh_bike_feature_tow, ';');
    bh_bike_feature_bkw_array := string_to_array(bh_bike_feature_bkw, ';');

    IF lup_base_type_array IS NOT NULL THEN
        FOR i IN 1..array_length(lup_base_type_array, 1) LOOP
            IF edge_category = 'B' THEN
                indicator_values := array_append(indicator_values, 1);
            ELSEIF (edge_category = 'L' OR functional_class = 2) AND edge_category <> 'B' THEN
                indicator_values := array_append(indicator_values, 2);
            ELSEIF ((edge_category = 'G' AND functional_class >= 3) OR
                    (edge_category = 'R' AND functional_class BETWEEN 3 AND 5) OR
                    (edge_category NOT IN ('B', 'L') AND functional_class BETWEEN 3 AND 5)) AND
                   (bh_bike_feature_tow_array[i] <> 'VK_BE' AND bh_bike_feature_bkw_array[i] <> 'VK_BE' AND
                    bh_bike_feature_tow_array[i] <> 'FRS' AND bh_bike_feature_bkw_array[i] <> 'FRS') AND
                   (access_car_ft OR access_car_tf) THEN
                indicator_values := array_append(indicator_values, 3);
            ELSEIF edge_category NOT IN ('B', 'L', 'G') AND functional_class > 5 AND
                   (bh_bike_feature_tow_array[i] <> 'VK_BE' AND bh_bike_feature_bkw_array[i] <> 'VK_BE' AND
                    bh_bike_feature_tow_array[i] <> 'FRS' AND bh_bike_feature_bkw_array[i] <> 'FRS') AND
                   (access_car_ft OR access_car_tf) THEN
                indicator_values := array_append(indicator_values, 4);
            ELSEIF (bh_bike_feature_tow_array[i] = 'VK_BE' OR bh_bike_feature_bkw_array[i] = 'VK_BE' OR
                    bh_bike_feature_tow_array[i] = 'FRS' OR bh_bike_feature_bkw_array[i] = 'FRS') AND
                   (access_car_ft OR access_car_tf) THEN
                indicator_values := array_append(indicator_values, 5);
            ELSEIF (bh_bike_feature_tow_array[i] = 'FUZO' OR bh_bike_feature_bkw_array[i] = 'FUZO') OR
                   ((access_car_ft IS FALSE AND access_car_tf IS FALSE) AND (access_bicycle_ft OR access_bicycle_tf) AND
                    lup_base_type_array[i] <> '7') THEN
                indicator_values := array_append(indicator_values, 6);
            ELSEIF (access_bicycle_ft IS FALSE AND access_bicycle_tf IS FALSE) OR lup_base_type_array[i] = '7' THEN
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
                WHEN '7' = ANY (indicator_values) THEN 'track'
            END;
    END IF;

    RETURN indicator_value;
END;
$$ LANGUAGE plpgsql;