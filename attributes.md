# Attributes / Indicators

Attributes / Indicators describe a certain property of a road segment.
Attributes / Indicators indicated with an asterisk (*) are differentiated by direction (ft/tf).
Indicators are used for index calculation.   

## Attributes

### access_car\_* / access_bicycle\_* / access_pedestrian\_*

Indicates the accessibility of a road segment for cars, bicycles or pedestrians: `true`, `false`

### bridge

Indicates a bridge on a road segment: `true`, `false`

### tunnel

Indicates a tunnel on a road segment: `true`, `false`

## Indicators

### bicycle_infrastructure_*

Describes the existence of dedicated bicycle infrastructure: `bicycle_way`, `mixed_way`, `bicycle_road`, `cyclestreet`, `bicycle_lane`, `bus_lane`, `no`.

### buildings

Describes the proportion of the area of buildings within a 30 meters buffer: `0` to `100`.


### crossings

Describes the amount of crossings within a 10 meters buffer.


### designated_route_*

Describes the existence of designated cycling routes categorized by impact: `local`, `regional`, `national`, `international`, `unknown`, `no`.


### facilities

Describes the amount of facilities (POIs) within a 30 meters buffer.


### gradient_*

Describes the gradient class of a road segment for downhill and uphill: `-4` to `4`.

| Class | Definition  |
|-------|-------------|
| 0     | 0 - 1,5 %   |
| 1     | > 1,5 - 3 % |
| 2     | > 3 - 6 %   |
| 3     | > 6 - 12 %  |
| 4     | > 12 %      |

The influence of gradient classes on the final index can be assigned per mode using the section `indicator_mapping` within mode profile files.


### greenness

Describes the proportion of the green area within a 30 meters buffer: `0` to `100`.


### max_speed\_* / max_speed_greatest

`max_speed_*` describes the speed limit (car) in the direction of travel or the average speed (car), if speed limit is not available: `0` to `130`. `max_speed_greatest_*` uses the maximum value of speed limits for both directions of travel on this segment.


### noise

Describes the noise level of a road segment in decibel.


### number_lanes_*

Describes the number of lanes of a road segment.


### parking_* (not in use)

Describes designated parking lots: `yes`, `no`. Currently, this indicator is not computed due to data availability. This will be documented accordingly in the `index_<mode>_*_robustness`-column in the output dataset.


### pavement

Describes the condition of the road surface: `asphalt`, `gravel`, `cobble`, `soft`.


### pedestrian_infrastructure_*

Describes the existence of dedicated pedestrian infrastructure: `pedestrian_area`, `pedestrian_way`, `mixed_way`, `stairs`, `sidewalk`, `no`.


### road_category

Describes the road category of a road segment: `primary`, `secondary`, `residential`, `service`, `calmed`, `no_mit`, `track`.


### water

Describes the occurrence of water bodies within a 30 meters buffer: `true`, `false`.


### width

Describes the width of a road segment in meters.
