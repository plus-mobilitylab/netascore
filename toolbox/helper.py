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
lineT = "-"*40
lineTime = "-"*11

verbose_level = LOG_LEVEL_2_INFO

# level: debug message detail level - 1: Major info - 2: INFO - 3: Detailed - 4: Debug level
def log(msg: str, level=LOG_LEVEL_3_DETAILED, elapsed = None):
    if(verbose_level < level):
        return
    if(level < LOG_LEVEL_4_DEBUG):
        # print (line)
        print (secondsToStr(clock()), '-', msg)
    else:
        print(msg)
    if elapsed:
        print ("Elapsed time:", elapsed)
    if(level < LOG_LEVEL_3_DETAILED):
        print (line)

# shorthand functions 

def majorInfo(msg: str):
    log(msg, LOG_LEVEL_1_MAJOR_INFO)

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
    print()
    print(line)
    print(">>> at", dt.now().strftime('%H:%M:%S'), ">>> ", s, "")
    startT = clock()

def logEndTask():
    global taskS, startT
    if taskS is None:
        return
    print(">>> ", taskS, "completed.")
    print(lineT)
    print(lineTime, "took", secondsToStr(clock()-startT, detailed=True), lineTime)
    print(line)
    print()
    taskS = None

def endlog():
    end = clock()
    elapsed = end-start
    info("Thank you for using NetAScore!")
    info(f"Program terminating after {secondsToStr(elapsed)} (hr:min:sec) at {dt.now().strftime('%H:%M:%S')}.")

def now():
    return secondsToStr(clock())

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
        log("No override parameters given -> skipping.")
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
    for key in keys:
        if key not in settings:
            log(f"key '{key}' not provided.", loglevel)
            return False
    return True

def has_any_key(settings: dict, keys: List[str], loglevel: int = 4) -> bool:
    for key in keys:
        if key in settings:
            return True
    log(f"None of the following keys were provided: {keys}", loglevel)
    return False


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