from functools import reduce
import atexit
from time import perf_counter as clock
import sys
from typing import List
from datetime import datetime as dt
import re

### LOGGING ###

LOG_LEVEL_4_DEBUG = 4
LOG_LEVEL_3_DETAILED = 3
LOG_LEVEL_2_INFO = 2
LOG_LEVEL_1_MAJOR_INFO = 1

def secondsToStr(t, detailed:bool = False):
    # more detailed: %d:%02d:%02d.%03d
    if detailed:
        return "%d:%02d:%02d.%03d" % \
        reduce(lambda ll,b : divmod(ll[0],b) + ll[1:],
            [(t*1000,),1000,60,60])

    return "%d:%02d:%02d" % \
        reduce(lambda ll,b : divmod(ll[0],b) + ll[1:],
            [(t,),60,60])

line = "="*40

verbose_level = LOG_LEVEL_2_INFO

# level: debug message detail level - 1: Major info - 2: INFO - 3: Detailed - 4: Debug level
def log(msg: str, level=LOG_LEVEL_3_DETAILED, elapsed = None):
    if(verbose_level < level):
        return
    if(level < LOG_LEVEL_4_DEBUG):
        print (dt.now().strftime('%H:%M:%S'), '-', msg)
    else:
        print(msg)
    if elapsed:
        print ("Elapsed time:", elapsed)

# shorthand functions 

def majorInfo(msg: str):
    log(msg, LOG_LEVEL_1_MAJOR_INFO)

def section(msg: str):
    """Logs the heading of a new section (e.g. processing step) with a separator line above."""
    print (line)
    majorInfo(msg)

FILE_VERSION = 2.0

def require_file_version(document: dict, filepath: str, example: str) -> None:
    version = document.get("version") if isinstance(document, dict) else None
    try:
        current = float(version)
    except (TypeError, ValueError):
        current = None
    if current is not None and current >= FILE_VERSION:
        return
    found = "missing" if version is None else version
    majorInfo(f"{filepath}: version is {found}. NetAScore 2.0 requires version {FILE_VERSION}. See {example}.")
    sys.exit(1)

def info(msg: str):
    log(msg, LOG_LEVEL_2_INFO)

def debugLog(msg: str):
    log(msg, LOG_LEVEL_4_DEBUG)

# task logging with time tracking

def logBeginTask(s, level = LOG_LEVEL_2_INFO):
    global startT, taskS
    if(verbose_level < level):
        return
    taskS = s
    print(dt.now().strftime('%H:%M:%S'), '>>>', s)
    startT = clock()

def logEndTask():
    global taskS, startT
    if taskS is None:
        return
    print(dt.now().strftime('%H:%M:%S'), '<<<', taskS, f"completed (took {secondsToStr(clock()-startT, detailed=True)})")
    taskS = None

def endlog():
    end = clock()
    elapsed = end-start
    info("Thank you for using NetAScore!")
    info(f"Program terminating after {secondsToStr(elapsed)} (hr:min:sec) at {dt.now().strftime('%H:%M:%S')}.")

def now():
    return dt.now().strftime('%H:%M:%S')

def get_current_log_level():
    return verbose_level

start = clock()
startT = clock()
taskS = None
atexit.register(endlog)
log("Program started.")


### other helper functions

def overrideParams(orig: dict, override: dict) -> dict:
    if orig == None:
        raise Exception("ERROR: original dict is None!")
    if override == None:
        debugLog("No override parameters given -> skipping.")
        return orig
    result = orig.copy()
    log("Replacing default parameter values with given override values")
    for key in override:
        log(f"{key}: {override[key]}")
        if key in result:
            log(f" -> replacing original value '{result[key]}' with '{override[key]}'")
            result[key] = override[key]
        else:
            log(f" -> key '{key}' does not exist. Skipping.")
    return result


def require_keys(settings: dict, required_keys: List[str], error_message: str = "A required settings key was not provided. Terminating."):
    if not has_keys(settings, required_keys, loglevel=1):
        majorInfo(error_message)
        sys.exit(1)

def has_keys(settings: dict, keys: List[str], loglevel: int = 4) -> bool:
    # empty settings sections (e.g. 'index:' without content) are loaded as None by YAML
    if not isinstance(settings, dict):
        log(f"keys {keys} not provided (settings section is empty).", loglevel)
        return False
    for key in keys:
        if key not in settings:
            log(f"key '{key}' not provided.", loglevel)
            return False
    return True

def has_any_key(settings: dict, keys: List[str], loglevel: int = 4) -> bool:
    if isinstance(settings, dict):
        for key in keys:
            if key in settings:
                return True
    log(f"None of the following keys were provided: {keys}", loglevel)
    return False

def get_section(settings: dict, key: str) -> dict:
    """Returns the given settings section as dict (empty dict if the section is missing or empty)."""
    if not isinstance(settings, dict):
        return {}
    section = settings.get(key)
    return section if isinstance(section, dict) else {}

def warn_unknown_keys(settings: dict, known_keys: List[str], context: str) -> None:
    """Logs a warning for keys that are not known (e.g. typos), as these are ignored."""
    if not isinstance(settings, dict):
        return
    for key in settings:
        if key not in known_keys:
            majorInfo(f"WARNING: unknown key '{key}' in {context} - it will be ignored. Known keys: {', '.join(known_keys)}")

def parse_bbox(value, setting_name: str = "bbox") -> List[float]:
    """Parses a bounding box given as list or comma-separated string in the order
    min lat, min lon, max lat, max lon (WGS84), e.g. '47.75, 12.98, 47.86, 13.12' or [47.75, 12.98, 47.86, 13.12]."""
    parts = value.split(",") if isinstance(value, str) else value
    try:
        bbox = [float(str(v).strip()) for v in parts]
    except (TypeError, ValueError):
        bbox = []
    if len(bbox) != 4:
        raise Exception(f"Unable to interpret the given '{setting_name}' value '{value}'. "
                        "It needs to contain min lat, min lon, max lat, max lon (WGS84), e.g. '47.75, 12.98, 47.86, 13.12' or [47.75, 12.98, 47.86, 13.12].")
    min_lat, min_lon, max_lat, max_lon = bbox
    if not (-90 <= min_lat < max_lat <= 90 and -180 <= min_lon < max_lon <= 180):
        raise Exception(f"Invalid '{setting_name}' value '{value}': expected min lat, min lon, max lat, max lon (in WGS84)")
    return bbox

# reuse: reuse existing data if it matches the settings of currently available data (otherwise error)
# reuse_or_overwrite: reuse existing data if it matches the current settings (otherwise overwrite)
# overwrite: always overwrite existing data, abort: stop if data exists
# NOTE: data without a recorded origin, e.g. results of processing steps, is reused without checks (for 'reuse' and 'reuse_or_overwrite')
ON_EXISTING_VALUES = ['reuse', 'reuse_or_overwrite', 'overwrite', 'abort']
ON_EXISTING_ALIASES = {'skip': 'reuse', 'delete': 'overwrite'}  # names used before NetAScore 2.0

def normalize_on_existing(value, context: str, default: str = 'abort') -> str:
    """Returns the 'on_existing' value ('reuse', 'reuse_or_overwrite', 'overwrite', or 'abort'); old names ('skip', 'delete') are translated."""
    if value is None or str(value).strip() == '':
        return default
    v = str(value).strip().lower()
    if v in ON_EXISTING_ALIASES:
        info(f"'on_existing: {v}' in {context} was renamed to '{ON_EXISTING_ALIASES[v]}' - please update your settings file.")
        v = ON_EXISTING_ALIASES[v]
    if v not in ON_EXISTING_VALUES:
        majorInfo(f"error: invalid value '{value}' for 'on_existing' in {context}. Allowed values: {', '.join(ON_EXISTING_VALUES)}")
        sys.exit(1)
    return v

def get_clip_mode(settings: dict) -> str:
    """Returns the clip mode from the import settings: 'bbox' (default), 'aoi', or 'none'."""
    clip_mode = 'bbox'
    if settings and 'clip' in settings:
        clip_mode = str(settings['clip']).strip().lower()
    if clip_mode not in ['bbox', 'aoi', 'none']:
        raise Exception(f"Invalid value '{clip_mode}' for import setting 'clip'. Allowed values: [bbox/aoi/none]")
    return clip_mode


# helper functions for parsing user input / settings values - sqlsafe

def is_numeric(value) -> bool:
    return type(value) in [int, float]

def get_safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "", value)

def get_safe_string(value) -> str:
    v = str(value)
    return re.sub(r"[^a-zA-Z0-9_.: \-]", "", v)

def str_to_numeric(value: str, throw_error: bool = False):
    v = re.sub(r"[^0-9.\-]", "", value) # extract value
    if v.find(".") > -1:
        return float(v)
    elif len(v) > 0:
        return int(v)
    if throw_error:
        raise Exception(f"Unable to convert string '{value}' to numeric.")
    return None

def str_is_numeric_only(value: str) -> bool:
    return True if re.fullmatch(r"[ 0-9.\-]+" ,value) else False