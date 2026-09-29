#!/usr/bin/env python3

import sys
import time
import googleapiclient.discovery
from google.oauth2 import service_account

# === BASIC SETTINGS ===
PROJECT_ID = "lab5-programmable-cloud-510117"
ZONE = "us-central1-a"
VM_LAUNCHER = "vm1-launcher"
VM_TARGET = "vm2-flask-app"
MACHINE_TYPE = "e2-micro"
IMAGE_FAMILY = "ubuntu-2204-lts"
IMAGE_PROJECT = "ubuntu-os-cloud"
SERVICE_KEY_PATH = 'service-account-key.json'

# === AUTHENTICATION ===
print("Initializing service account authentication...")
try:
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_KEY_PATH,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
except FileNotFoundError:
    print(f"ERROR: Missing credentials file: {SERVICE_KEY_PATH}")
    sys.exit(1)
print("Authentication successful")

compute = googleapiclient.discovery.build('compute', 'v1', credentials=creds)

# === VM-2 STARTUP SCRIPT ===
VM2_SCRIPT = """#!/bin/bash
set -e
exec > >(tee -a /var/log/vm2-init.log)
exec 2>&1

echo "== Starting Flask setup on VM-2 =="
mkdir -p /opt/flask-app && cd /opt/flask-app

apt-get update -y
apt-get install -y python3 python3-pip git python3-venv

git clone https://github.com/pallets/flask.git flask-tutorial
cd /opt/flask-app/flask-tutorial/examples/tutorial

python3 -m venv venv
source venv/bin/activate
pip install -e .
pip install flask

export FLASK_APP=flaskr
python3 -m flask --app flaskr init-db

nohup python3 -m flask --app flaskr run -h 0.0.0.0 --port 5000 > /var/log/flask.log 2>&1 &
echo "== Flask app launched =="
"""

# === VM-1 LAUNCHER SCRIPT ===
VM1_SCRIPT = f"""#!/usr/bin/env python3
import time
import requests
from google.oauth2 import service_account
import googleapiclient.discovery

METADATA_URL = "http://metadata.google.internal/computeMetadata/v1"
HEADERS = {{"Metadata-Flavor": "Google"}}

project_id = requests.get(f"{{METADATA_URL}}/project/project-id", headers=HEADERS).text

creds = service_account.Credentials.from_service_account_file(
    '/srv/service-credentials.json',
    scopes=['https://www.googleapis.com/auth/cloud-platform']
)
compute = googleapiclient.discovery.build('compute', 'v1', credentials=creds)

with open('/srv/vm2-startup-script.sh') as s:
    startup_script = s.read()

config = {{}}
with open('/srv/config.txt') as cfg:
    for line in cfg:
        k, v = line.strip().split('=')
        config[k] = v

zone = config['ZONE']
vm2_name = config['VM2_NAME']
machine = config['MACHINE_TYPE']

img = compute.images().getFromFamily(project='{IMAGE_PROJECT}', family='{IMAGE_FAMILY}').execute()
image_link = img['selfLink']

machine_url = f"zones/{{zone}}/machineTypes/{{machine}}"

vm2_conf = {{
    'name': vm2_name,
    'machineType': machine_url,
    'disks': [{{
        'boot': True,
        'autoDelete': True,
        'initializeParams': {{
            'sourceImage': image_link,
            'diskSizeGb': 10
        }}
    }}],
    'networkInterfaces': [{{
        'network': f'projects/{{project_id}}/global/networks/default',
        'accessConfigs': [{{'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}}]
    }}],
    'metadata': {{
        'items': [{{'key': 'startup-script', 'value': startup_script}}]
    }},
    'tags': {{'items': ['allow-5000']}}
}}

print(f"VM-1: Creating secondary VM '{{vm2_name}}'...")
op = compute.instances().insert(project=project_id, zone=zone, body=vm2_conf).execute()

while True:
    result = compute.zoneOperations().get(project=project_id, zone=zone, operation=op['name']).execute()
    if result['status'] == 'DONE':
        if 'error' in result:
            print(f"Error launching VM-2: {{result['error']}}")
        else:
            print("VM-2 successfully created.")
        break
    time.sleep(2)

inst = compute.instances().get(project=project_id, zone=zone, instance=vm2_name).execute()
ip = None
for iface in inst['networkInterfaces']:
    for cfg in iface.get('accessConfigs', []):
        if 'natIP' in cfg:
            ip = cfg['natIP']
            break

if ip:
    print(f"VM-2 IP: {{ip}}")
    with open('/srv/vm2-results.txt', 'w') as f:
        f.write(f"VM-2 External IP: {{ip}}\\nFlask URL: http://{{ip}}:5000\\n")
"""

# === VM-1 STARTUP SHELL SCRIPT ===
VM1_STARTUP = """#!/bin/bash
set -e
exec > >(tee -a /var/log/vm1-init.log)
exec 2>&1

echo "== VM-1 bootstrap started =="

mkdir -p /srv && cd /srv

curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/vm2-startup-script > vm2-startup-script.sh
curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/vm1-launch-script > vm1-launch-script.py
curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/service-credentials > service-credentials.json
curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/config > config.txt

apt-get update -y
apt-get install -y python3 python3-pip
pip3 install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib requests

python3 /srv/vm1-launch-script.py
echo "== VM-1 bootstrap complete =="
"""

# === HELPER FUNCTIONS ===
def await_operation(compute_service, project_id, zone, op_name):
    while True:
        resp = compute_service.zoneOperations().get(
            project=project_id, zone=zone, operation=op_name
        ).execute()
        if resp['status'] == 'DONE':
            if 'error' in resp:
                raise RuntimeError(resp['error'])
            return resp
        time.sleep(1)

def fetch_image(compute_service, img_project, family):
    return compute_service.images().getFromFamily(
        project=img_project, family=family
    ).execute()['selfLink']

# === MAIN LOGIC ===
def main():
    print("\n" + "="*60)
    print("   Part 3 — Automated VM Launcher")
    print("="*60)

    try:
        with open(SERVICE_KEY_PATH, 'r') as f:
            creds_content = f.read()
        config_data = f"ZONE={ZONE}\nVM2_NAME={VM_TARGET}\nMACHINE_TYPE={MACHINE_TYPE}\n"

        print("Retrieving base image...")
        image_link = fetch_image(compute, IMAGE_PROJECT, IMAGE_FAMILY)
        machine_url = f"zones/{ZONE}/machineTypes/{MACHINE_TYPE}"

        vm1_config = {
            'name': VM_LAUNCHER,
            'machineType': machine_url,
            'disks': [{
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceImage': image_link,
                    'diskSizeGb': 10
                }
            }],
            'networkInterfaces': [{
                'network': f'projects/{PROJECT_ID}/global/networks/default',
                'accessConfigs': [{'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}]
            }],
            'metadata': {
                'items': [
                    {'key': 'startup-script', 'value': VM1_STARTUP},
                    {'key': 'vm2-startup-script', 'value': VM2_SCRIPT},
                    {'key': 'vm1-launch-script', 'value': VM1_SCRIPT},
                    {'key': 'service-credentials', 'value': creds_content},
                    {'key': 'config', 'value': config_data}
                ]
            }
        }

        print(f"Launching primary VM: {VM_LAUNCHER}")
        op = compute.instances().insert(project=PROJECT_ID, zone=ZONE, body=vm1_config).execute()
        await_operation(compute, PROJECT_ID, ZONE, op['name'])

        inst = compute.instances().get(project=PROJECT_ID, zone=ZONE, instance=VM_LAUNCHER).execute()
        vm1_ip = None
        for iface in inst['networkInterfaces']:
            for cfg in iface.get('accessConfigs', []):
                if 'natIP' in cfg:
                    vm1_ip = cfg['natIP']
                    break

        print(f"\nVM-1 created successfully. External IP: {vm1_ip}")
        print(f"VM-1 will now spawn VM-2 '{VM_TARGET}'. This process takes ~3-5 minutes.")

    except Exception as e:
        print(f"\n[Exception] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()