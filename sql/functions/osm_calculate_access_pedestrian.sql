CREATE OR REPLACE FUNCTION calculate_access_pedestrian(
    access character varying,
    foot character varying,
    footway character varying,
    sidewalk character varying,
    highway character varying
)
RETURNS int AS $BODY$
	DECLARE
	    ped_access int;
	BEGIN
	    ped_access:=case
	        -- check foot, footway, and sidewalk attributes
	        when foot='yes' or footway='yes' or sidewalk='yes'
	            then 1 -- allow access
	        when foot='no' or footway='no'
	            then 0 -- restrict access
			-- check global access restrictions
	        when access='no'
	            then 0 -- restrict access
	        when highway='no' or highway is null
	            then 0 -- restrict access
	        else 1 -- allow access
	    end;
        RETURN ped_access;
	END;
$BODY$ LANGUAGE plpgsql;
