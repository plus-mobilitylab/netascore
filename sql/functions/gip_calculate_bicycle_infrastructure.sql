CREATE OR REPLACE FUNCTION calculate_bicycle_infrastructure(
    basetype varchar, bikefeature varchar
)
RETURNS varchar AS $$
DECLARE
    basetype_array    varchar[];
    bikefeature_array varchar[];
    indicator_values  integer[];
    indicator_value   varchar;
BEGIN
    basetype_array := string_to_array(basetype, ';');
    bikefeature_array := string_to_array(bikefeature, ';');

    IF basetype_array IS NOT NULL THEN
        FOR i IN 1..array_length(basetype_array, 1) LOOP
            IF bikefeature_array[i] IN ('RW', 'RWO') THEN
                indicator_values := array_append(indicator_values, 1);
            ELSEIF (bikefeature_array[i] IN ('GRW_T', 'GRW_TO', 'GRW_M', 'GRW_MO') AND basetype_array[i] <> '7') THEN
                indicator_values := array_append(indicator_values, 2);
            ELSEIF bikefeature_array[i] IN ('MZSTR', 'RF') THEN
                indicator_values := array_append(indicator_values, 3);
            ELSEIF bikefeature_array[i] IN ('BS') THEN
                indicator_values := array_append(indicator_values, 4);
            END IF;
        END LOOP;

        indicator_value :=
            CASE
                WHEN 1 = ANY (indicator_values) THEN 'bicycle_way'
                WHEN 2 = ANY (indicator_values) THEN 'mixed_way'
                WHEN 3 = ANY (indicator_values) THEN 'bicycle_lane'
                WHEN 4 = ANY (indicator_values) THEN 'bus_lane'
                ELSE 'no'
            END;
    END IF;

    RETURN indicator_value;
END;
$$ LANGUAGE plpgsql;