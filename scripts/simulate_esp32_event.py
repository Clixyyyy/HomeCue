"""Send a harmless simulated lab event through the device endpoint.
Usage: set HC_HOME_ID, HC_DEVICE_TOKEN, HC_SERVER_URL, then run this script.
Unlike the website's demo events, these are device-API test traffic, explicitly marked TEST.
"""
from __future__ import annotations
import json, os, sys, urllib.error, urllib.request

base = os.getenv('HC_SERVER_URL', 'http://127.0.0.1:8000').rstrip('/')
home_id = os.getenv('HC_HOME_ID', '')
token = os.getenv('HC_DEVICE_TOKEN', '')
if not home_id.isdigit() or not token:
    print('Set HC_HOME_ID and HC_DEVICE_TOKEN first. See README_START_HERE.md.')
    sys.exit(2)


def send(path: str, payload: dict):
    url = f'{base}{path}'
    req = urllib.request.Request(url, json.dumps(payload).encode(), {'X-Device-Token': token, 'Content-Type':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as err:
        print('HTTP error:', err.code, err.read().decode())
        raise


print('Heartbeat:', send(f'/api/device/{home_id}/heartbeat', {}))
print('Event:', send(f'/api/device/{home_id}/events', {'module':'task','kind':'test_ping','message':'TEST ONLY: script sent a simulated RFID observation'}))
print('Open website Activity or the Flutter Activity tab to see the test event.')
