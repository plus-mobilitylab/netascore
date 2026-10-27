CREATE OR REPLACE FUNCTION calculate_bicycle_infrastructure(
    lu_basetype varchar, bh_bikefeature varchar,
    access_car_ft boolean, access_car_tf boolean
)
RETURNS varchar AS $$
DECLARE
    lu_basetype_array    varchar[];
    bh_bikefeature_array varchar[];
    indicator_values  integer[];
    indicator_value   varchar;
BEGIN
    lu_basetype_array := string_to_array(lu_basetype, ';');
    bh_bikefeature_array := string_to_array(bh_bikefeature, ';');

    IF lu_basetype_array IS NOT NULL THEN -- TODO: condition correct?
        FOR i IN 1..array_length(lu_basetype_array, 1) LOOP
            IF bh_bikefeature_array[i] IN ('RW', 'RWO') OR
               (bh_bikefeature_array[i] = 'FRS' AND access_car_ft IS FALSE AND access_car_tf IS FALSE) THEN
                indicator_values := array_append(indicator_values, 1);
            ELSEIF (bh_bikefeature_array[i] IN ('GRW_T', 'GRW_TO', 'GRW_M', 'GRW_MO') AND lu_basetype_array[i] <> '7') THEN
                indicator_values := array_append(indicator_values, 2);
            ELSEIF bh_bikefeature_array[i] IN ('MZSTR', 'RF') THEN
                indicator_values := array_append(indicator_values, 3);
            ELSEIF bh_bikefeature_array[i] IN ('BS') THEN
                indicator_values := array_append(indicator_values, 4);
            ELSEIF bh_bikefeature_array[i] IN ('FRS') THEN
                indicator_values := array_append(indicator_values, 5);
            END IF;
        END LOOP;

        indicator_value :=
            CASE
                WHEN 1 = ANY (indicator_values) THEN 'bicycle_way'
                WHEN 2 = ANY (indicator_values) THEN 'mixed_way'
                WHEN 3 = ANY (indicator_values) THEN 'bicycle_lane'
                WHEN 4 = ANY (indicator_values) THEN 'bus_lane'
                WHEN 5 = ANY (indicator_values) THEN 'bicycle_road'
                ELSE 'no'
            END;
    END IF;

    RETURN indicator_value;
END;
$$ LANGUAGE plpgsql;
