from functools import reduce
import atexit
from time import perf_counter as clock

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
    print(">>> ", s, "")
    startT = clock()

def logEndTask():
    global taskS, startT
    print(">>> ", taskS, "completed.")
    print(lineT)
    print(lineTime, "took", secondsToStr(clock()-startT, detailed=True), lineTime)
    print(line)
    print()

def endlog():
    end = clock()
    elapsed = end-start
    log(f"Program terminating after {secondsToStr(elapsed)} (hr:min:sec).")

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