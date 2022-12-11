CREATE OR REPLACE FUNCTION calculate_bicycle_infrastructure(
    basetype varchar, bikefeature varchar -- bikesigned varchar, designated_route varchar
)
RETURNS varchar AS $$
DECLARE
    basetype_array    varchar[];
    -- bikesigned_array  varchar[]
    bikefeature_array varchar[];
    indicator_values  integer[];
    indicator_value   varchar;
BEGIN
    basetype_array := string_to_array(basetype, ';');
    -- bikesigned_array := string_to_array(bikesigned, ';');
    bikefeature_array := string_to_array(bikefeature, ';');

    IF basetype_array IS NOT NULL THEN -- TODO: condition correct?
        FOR i IN 1..array_length(basetype_array, 1) LOOP
            IF bikefeature_array[i] IN ('RW', 'RWO') THEN
                indicator_values := array_append(indicator_values, 1);
            ELSEIF (bikefeature_array[i] IN ('GRW_T', 'GRW_TO', 'GRW_M', 'GRW_MO') AND basetype_array[i] <> '7') THEN
				   -- (bikesigned_array[i] = '1' and basetype_array[i] <> '1') OR -- TODO: adaptation to client
				   -- (basetype_array[i] = '7' and designated_route <> 'no') -- TODO: adaptation to client
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