import asyncio
import multiprocessing
import multiprocessing.pool
import random
import sys
import threading
import time
import traceback

import masscan as msCan
import pymongo

import funcs

useWebHook, pingsPerSec, maxActive = False, 4800, 10
masscan_search_path = (
    "masscan",
    "/usr/bin/masscan",
    "/usr/local/bin/masscan",
    "/sw/bin/masscan",
    "/opt/local/bin/masscan",
)
try:
    from privVars import *
except ImportError:
    MONGO_URL = "mongodb+srv://..."
    DSICORD_WEBHOOK = "discord.api.com/..."


if MONGO_URL == "mongodb+srv://...":
    print("Please add your mongo url to privVars.py")
    input()
    sys.exit()
if useWebHook and DSICORD_WEBHOOK == "discord.api.com/...":
    print("Please add your discord webhook to privVars.py")
    input()
    sys.exit()

# Setup
# ---------------------------------------------

DEBUG = True

time_start = time.time()
threads = []
pool = multiprocessing.pool.ThreadPool(maxActive)

client = pymongo.MongoClient(
    MONGO_URL, server_api=pymongo.server_api.ServerApi("1")
)  # type: ignore
db = client["mc"]
col = db["servers"]
fncs = funcs.funcs(collection=col)

# Funcs
# ---------------------------------------------


def print(*args, **kwargs):
    fncs.print(" ".join(map(str, args)), **kwargs)


def check(host):
    if useWebHook:
        return fncs.check(host, webhook=DSICORD_WEBHOOK)
    else:
        return fncs.check(host)


def scan(ip_list):
    try:
        scanner = msCan.PortScanner(masscan_search_path=masscan_search_path)
    except msCan.PortScannerError:
        print("Masscan not found, please install it")
        return []

    try:
        import json

        scanner.scan(
            ip_list,
            ports="25565",
            arguments="--max-rate {}".format(pingsPerSec / maxActive),
            sudo=True,
        )
        result = json.loads(scanner.scan_result)  # type: ignore

        return list(result["scan"].keys())
    except OSError:
        sys.exit(0)
    except Exception:
        Eprint(traceback.format_exc())
        return []


def Eprint(text):
    """Error printer

    Args:
        text (String): Error text
    """
    text = str(text)
    (disLog("Error: " + "".join(str(i) for i in text))) if useWebHook else None
    fncs.dprint("\n" + "".join(str(i) for i in text) + "\n")


def disLog(text, end="\r"):
    if useWebHook:
        try:
            import requests

            url = DSICORD_WEBHOOK
            data = {"content": text + end}
            requests.post(url, data=data)
        except Exception:
            Eprint(text + "\n" + traceback.format_exc())


async def threader(ip_range):
    try:
        ips = scan(ip_range)

        if len(ips) > 0:
            pool = multiprocessing.pool.ThreadPool(maxActive // 2)
            pool.map(check, ips)
    except OSError:
        sys.exit(0)
    except Exception:
        Eprint(traceback.format_exc())


def crank(ip_range):
    asyncio.run(threader(ip_range))


# Main
# ---------------------------------------------

# create a list of ipv4 ranges
ip_lists = []
for i in range(255):
    for j in range(255):
        ip_lists.append(f"{i}.{j}.0.0/16")
random.shuffle(ip_lists)

ip_lists = ip_lists[:1000]  # remove for final version
time.sleep(0.5)

tStart = time.time()
normal = threading.active_count()


async def makeThreads():
    # Create a thread for each list of IPs
    for ip_list in ip_lists:
        # check to make sure that more than 2*maxActive threads haven't been created in the last 1 second
        if len(threads) >= maxActive * 2 and time.time() - tStart <= 1:
            await asyncio.sleep(0.5)
            Eprint(
                "Too many threads spawned to quickly, exiting\nPlease check the console and logs for more details"
            )
            sys.exit()

        t = threading.Thread(
            target=crank, args=(ip_list,), name=f"Scan func thread: {ip_list}"
        )

        threads.append(t)

        # If the number of active threads is greater than the max, sleep for 0.1 seconds
        while threading.active_count() - normal >= maxActive:
            await asyncio.sleep(0.1)
        t.start()


if __name__ == "__main__":
    asyncio.run(makeThreads())
