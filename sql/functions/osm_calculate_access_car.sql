CREATE OR REPLACE FUNCTION calculate_access_car(
    direction character varying,
    access character varying,
    motor_vehicle_fwd_bkw character varying,
    oneway character varying,
    oneway_motor_vehicle character varying,
    oneway_vehicle character varying,
    roundabout character varying,
    motor_vehicle character varying,
    motorcar character varying,
    vehicle_fwd_bkw character varying,
    vehicle character varying,
    highway character varying
)
RETURNS int AS $BODY$
	DECLARE
	    car_access int;
	BEGIN
	    car_access:=case
            -- check motor vehicle forward restrictions and permissions
            when motor_vehicle_fwd_bkw='yes'
                then 1 -- allow access
            when motor_vehicle_fwd_bkw='no'
                then 0 -- restrict access
            -- check oneway restrictions
            when (direction='ft' and (oneway='opposite' or oneway_motor_vehicle='opposite' or oneway_vehicle='opposite')) or
                 (direction='tf' and (oneway='yes' or oneway_motor_vehicle='yes' or oneway_vehicle='yes'))
                then 0 -- restrict access
            -- check roundabout restrictions
               when direction='tf' and roundabout='yes'
                   then 0 -- restrict access
            -- check motor_vehicle and motorcar restrictions and permissions
            when motor_vehicle='yes' or motorcar='yes'
                then 1 -- allow access
            when motor_vehicle='no' or motorcar='no'
                then 0 -- restrict access
            -- check vehicle_forward restrictions
            when vehicle_fwd_bkw='no'
                then 0 -- restrict access
            -- check vehicle restrictions
            when vehicle='no'
                then 0 -- restrict access
            -- check global access restrictions
            when access='no'
                then 0 -- restrict access
            -- check highway restrictions
            when highway='no' or highway is null
                then 0 -- restrict access
            else 1
	    end;
        RETURN car_access;
	END;
$BODY$ LANGUAGE plpgsql;



