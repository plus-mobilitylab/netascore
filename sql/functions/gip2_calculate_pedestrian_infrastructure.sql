CREATE OR REPLACE FUNCTION calculate_gip2_pedestrian_infrastructure(
    base_type varchar, bike_feature varchar,
    form_of_way integer, access_pedestrian boolean
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

    IF base_type_array IS NOT NULL THEN
        FOR i IN 1..array_length(base_type_array, 1) LOOP
            IF form_of_way = '14' AND base_type_array[i] IN ('1', '7') THEN
                indicator_values := array_append(indicator_values, 1);
            ELSEIF base_type_array[i] = '7' THEN
                indicator_values := array_append(indicator_values, 2);
            ELSEIF base_type_array[i] <> '7' AND bike_feature_array[i] IN ('GRW_M', 'GRW_MO') AND access_pedestrian THEN
                indicator_values := array_append(indicator_values, 3);
            ELSEIF base_type_array[i] IN ('6', '13', '24', '25', '42') THEN
                indicator_values := array_append(indicator_values, 4);
            ELSEIF access_pedestrian AND base_type_array[i] = '1' THEN -- TODO: access_pedestrian is true for both directions when there is only a sidewalk on one side of the road
                indicator_values := array_append(indicator_values, 5);
            END IF;
        END LOOP;

        indicator_value :=
            CASE
                WHEN 1 = ANY (indicator_values) THEN 'pedestrian_area' -- 'fuzo'
                WHEN 2 = ANY (indicator_values) THEN 'pedestrian_way' -- 'pedestrians_separated'
                WHEN 3 = ANY (indicator_values) THEN 'mixed_way' -- 'mixed'
                WHEN 4 = ANY (indicator_values) THEN 'stairs'
                WHEN 5 = ANY (indicator_values) THEN 'sidewalk'
                ELSE 'no'
            END;
    END IF;

    RETURN indicator_value;
END;
$$ LANGUAGE plpgsql;