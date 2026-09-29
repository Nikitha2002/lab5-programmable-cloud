#!/usr/bin/env python3
import time
from google.cloud import compute_v1
import google.auth

# Authenticate automatically using your application default credentials
_, project = google.auth.default()

# Initialize compute API clients for instances and firewalls
instance_client = compute_v1.InstancesClient()
firewall_client = compute_v1.FirewallsClient()

ZONE = "us-central1-a"
MACHINE_TYPE = "e2-micro"
INSTANCE_NAME = "flask-vm"
FIREWALL_RULE = "allow-5000"
TAG = "allow-5000"

# Startup script that updates packages, clones the flask repo, and starts the server
STARTUP_SCRIPT = """#!/bin/bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip git
cd /home
git clone https://github.com/cu-csci-4253-datacenter/flask-tutorial
cd flask-tutorial
sudo python3 setup.py install
sudo pip3 install -e .
export FLASK_APP=flaskr
flask init-db
nohup flask run -h 0.0.0.0 &
"""

def create_firewall_rule():
    """Creates an ingress firewall rule allowing TCP traffic on port 5000."""
    try:
        # Create allowed rule for TCP on port 5000
        allowed_spec = compute_v1.Allowed()
        allowed_spec.I_P_protocol = "tcp"
        allowed_spec.ports = ["5000"]

        firewall_rule = compute_v1.Firewall(
            name=FIREWALL_RULE,
            allowed=[allowed_spec],
            target_tags=[TAG],
            source_ranges=["0.0.0.0/0"]
        )
        op = firewall_client.insert(project=project, firewall_resource=firewall_rule)
        op.result()
        print(f"Firewall rule '{FIREWALL_RULE}' created successfully.")
    except Exception as e:
        print(f"Firewall rule check/creation note: {e}")

def create_instance():
    """Creates an f1-micro Ubuntu instance with the startup script and network tag."""
    # 1. Boot disk configuration using Ubuntu 22.04 LTS
    disk = compute_v1.AttachedDisk(
        boot=True,
        auto_delete=True,
        initialize_params=compute_v1.AttachedDiskInitializeParams(
            source_image="projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts"
        )
    )

    # 2. Network Interface configuration with an External NAT IP
    network_interface = compute_v1.NetworkInterface(
        network="global/networks/default",
        access_configs=[compute_v1.AccessConfig(name="External NAT", type_="ONE_TO_ONE_NAT")]
    )

    # 3. Add Startup Script into instance metadata
    metadata = compute_v1.Metadata(
        items=[compute_v1.Items(key="startup-script", value=STARTUP_SCRIPT)]
    )

    # 4. Assemble instance specifications
    instance = compute_v1.Instance(
        name=INSTANCE_NAME,
        machine_type=f"zones/{ZONE}/machineTypes/{MACHINE_TYPE}",
        disks=[disk],
        network_interfaces=[network_interface],
        metadata=metadata,
        tags=compute_v1.Tags(items=[TAG])
    )

    print(f"Creating VM instance '{INSTANCE_NAME}' in zone {ZONE}...")
    op = instance_client.insert(project=project, zone=ZONE, instance_resource=instance)
    op.result()  # Wait until creation completes
    print(f"Instance '{INSTANCE_NAME}' created.")

def get_instance_ip():
    """Fetches and displays the external IP address of the created instance."""
    inst = instance_client.get(project=project, zone=ZONE, instance=INSTANCE_NAME)
    ip = inst.network_interfaces[0].access_configs[0].nat_i_p
    print("\n--------------------------------------------------")
    print(f"Flask application address: http://{ip}:5000")
    print("--------------------------------------------------")
    print("Note: The startup script may take 1-2 minutes to finish setting up Flask.")

if __name__ == "__main__":
    create_firewall_rule()
    create_instance()
    get_instance_ip()