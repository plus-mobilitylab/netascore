CREATE OR REPLACE FUNCTION calculate_access_bicycle(
    direction character varying,access character varying,
    bicycle_fwd_bkw character varying,
    oneway_bicycle character varying,
    roundabout character varying,
    oneway character varying,
    cycleway character varying,
    cycleway_right character varying,
    cycleway_left character varying,
    cycleway_both character varying,
    bicycle character varying,
    highway character varying
)
RETURNS int AS $BODY$
	DECLARE
	    bike_access int;
	BEGIN
	    bike_access:=case
            -- check bicycle_forward/bicycle_backward (depends on the direction) restrictions and permissions
            when bicycle_fwd_bkw='no'
                then 0 -- restrict access
            when bicycle_fwd_bkw='yes'
                then 1 -- allow access
            -- check oneway_bicycle restrictions and permissions
            when (direction='ft' and  oneway_bicycle='opposite') or (direction='tf' and oneway_bicycle='yes')
                then 0 -- restrict access
            when (direction='ft' and  oneway_bicycle='yes') or (direction='tf' and oneway_bicycle='opposite')
                then 1 -- allow access
            -- check roundabout restrictions for bkw direction
            when direction='tf' and roundabout='yes'
                then 0 -- restrict access
            -- check oneway restrictions and cycleway infrastructure in the opposite direction
            when (direction='ft' and  oneway='opposite'
                      and (cycleway!='yes' or cycleway is null)
                      and (cycleway_right!='yes' or cycleway_right is null)
                      and (cycleway_left!='opposite' or cycleway_left is null)
                      and (cycleway_both!='yes' or cycleway_both is null)) or
                 (direction='tf' and  oneway='yes'
                      and (cycleway!='opposite' or cycleway is null)
                      and (cycleway_right!='opposite' or cycleway_right is null)
                      and (cycleway_left!='yes' or cycleway_left is null)
                      and (cycleway_both!='yes' or cycleway_both is null))
                then 0 -- restrict access
            -- check bicycle permissions
            when bicycle='no'
                then 0 -- restrict access
            when bicycle='yes'
                then 1 -- allow access
            -- check global access restrictions
            when access='no'
                then 0 -- restrict access
            -- check highway restrictions
            when highway='no' or highway is null
                then 0 -- restrict access
            else 1 -- allow access
        end;
        RETURN bike_access;
	END;
$BODY$ LANGUAGE plpgsql;