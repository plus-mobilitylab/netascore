CREATE OR REPLACE FUNCTION calculate_gip2_bicycle_infrastructure(
    base_type varchar, bike_feature varchar
)
RETURNS varchar AS $$
DECLARE
    base_type_array    varchar[];
    bike_feature_array varchar[];
    indicator_values   integer[];
    indicator_value    varchar;
BEGIN
    base_type_array := string_to_array(base_type, ';');
    bike_feature_array := string_to_array(bike_feature, ';');

    IF base_type_array IS NOT NULL THEN -- TODO: condition correct?
        FOR i IN 1..array_length(base_type_array, 1) LOOP
            IF bike_feature_array[i] IN ('RW', 'RWO') THEN
                indicator_values := array_append(indicator_values, 1);
            ELSEIF (bike_feature_array[i] IN ('GRW_T', 'GRW_TO', 'GRW_M', 'GRW_MO') AND base_type_array[i] <> '7') THEN
                indicator_values := array_append(indicator_values, 2);
            ELSEIF bike_feature_array[i] IN ('MZSTR', 'RF') THEN
                indicator_values := array_append(indicator_values, 3);
            ELSEIF bike_feature_array[i] IN ('BS') THEN
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