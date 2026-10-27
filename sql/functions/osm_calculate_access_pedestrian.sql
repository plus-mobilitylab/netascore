CREATE OR REPLACE FUNCTION calculate_access_pedestrian(
    access character varying,
    foot character varying,
    sidewalk character varying,
    highway character varying
)
RETURNS int AS $BODY$
	DECLARE
	    ped_access int;
	BEGIN
	    -- strict access matching; ignore sidewalks mapped as separate ways here (these are considered in "pedestrian_infrastructure")
	    ped_access:=case
	        -- check foot restrictions and permissions
	        when foot='yes'
	            then 1 -- allow access
	        when foot='no'
	            then 0 -- restrict access
	        -- sidewalk on the way itself overrides general access restrictions
	        when sidewalk='yes'
	            then 1 -- allow access
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
