# Attributes / Indicators

Attributes / Indicators describe a certain property of a road segment.
Attributes / Indicators indicated with an asterisk (*) are differentiated by direction (ft/tf).
Indicators are used for index calculation.   

## Attributes

### access_car_* / access_bicycle_* / access_pedestrian_*

Indicates the accessibility of a road segment for cars, bicycles or pedestrians: `true`, `false`

### bridge

Indicates a bridge on a road segment: `true`, `false`

### tunnel

Indicates a tunnel on a road segment: `true`, `false`

## Indicators

### bicycle_infrastructure_*

Describes the existence of dedicated bicycle infrastructure: `bicycle_way`, `mixed_way`, `bicycle_lane`, `bus_lane`, `no`.

### buildings

Describes the proportion of the area of buildings within a 30 meters buffer: `0` to `100`.


### crossings

Describes the amount of crossings within a 10 meters buffer.


### designated_route_*

Describes the existence of designated cycling routes categorized by impact: `local`, `regional`, `national`, `international`, `unknown`, `no`.


### facilities

Describes the amount of facilities (POIs) within a 30 meters buffer.


### gradient_bicycle_* / gradient_pedestrian_*

Describes the gradient class of a road segment for downhill and uphill: `-4` to `4`.

| Class | Definition  |
|-------|-------------|
| 0     | 0 - 1,5 %   |
| 1     | > 1,5 - 3 % |
| 2     | > 3 - 6 %   |
| 3     | > 6 - 12 %  |
| 4     | > 12 %      |

Different internal weights are used for bikeability / walkability.


### greenness

Describes the proportion of the green area within a 30 meters buffer: `0` to `100`.


### max_speed_bicycle_* / max_speed_pedestrian_*

Describes the speed limit (car) or the average speed (car), if speed limit is not available: `0` to `130`.


### noise

Describes the noise level of a road segment in decibel.


### number_lanes_*

Describes the number of lanes of a road segment.


### parking_* (not in use)

Describes designated parking lots: `yes`, `no`.


### pavement

Describes the condition of the road surface: `asphalt`, `gravel`, `cobble`, `soft`.


### pedestrian_infrastructure_*

Describes the existence of dedicated pedestrian infrastructure: `pedestrian_area`, `pedestrian_way`, `mixed_way`, `stairs`, `sidewalk`, `no`.


### road_category_bicycle / road_category_pedestrian

Describes the road category of a road segment: `primary`, `secondary`, `residential`, `service`, `calmed`, `no_mit`, `path`.

Different internal weights are used for bikeability / walkability.


### water

Describes the occurrence of water bodies within a 30 meters buffer: `true`, `false`.


### width

Describes the width of a road segment in meters.
