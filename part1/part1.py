#!/usr/bin/env python3

from google.cloud import compute_v1
import google.auth


# Authenticate automatically using application default credentials
_, project = google.auth.default()


# Initialize Compute Engine API clients
instance_client = compute_v1.InstancesClient()
firewall_client = compute_v1.FirewallsClient()


ZONE = "us-central1-a"
MACHINE_TYPE = "f1-micro"
INSTANCE_NAME = "flask-vm"
FIREWALL_RULE = "allow-5000"
TAG = "allow-5000"


# Startup script that installs and starts the Flask tutorial application
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
    """Create allow-5000 firewall rule if it does not already exist."""

    try:
        # Check whether the firewall rule already exists
        firewall_client.get(
            project=project,
            firewall=FIREWALL_RULE
        )

        print(f"Firewall rule '{FIREWALL_RULE}' already exists.")

    except Exception:
        # Rule does not exist, so create it
        allowed_spec = compute_v1.Allowed(
            I_P_protocol="tcp",
            ports=["5000"]
        )

        firewall_rule = compute_v1.Firewall(
            name=FIREWALL_RULE,
            allowed=[allowed_spec],
            target_tags=[TAG],
            source_ranges=["0.0.0.0/0"]
        )

        op = firewall_client.insert(
            project=project,
            firewall_resource=firewall_rule
        )

        op.result()

        print(f"Firewall rule '{FIREWALL_RULE}' created successfully.")


def create_instance():
    """Create the VM instance with the Flask startup script."""

    # Boot disk configuration using Ubuntu 22.04 LTS
    disk = compute_v1.AttachedDisk(
        boot=True,
        auto_delete=True,
        initialize_params=compute_v1.AttachedDiskInitializeParams(
            source_image=(
                "projects/ubuntu-os-cloud/global/images/family/"
                "ubuntu-2204-lts"
            )
        )
    )

    # Network interface with an external NAT IP
    network_interface = compute_v1.NetworkInterface(
        network="global/networks/default",
        access_configs=[
            compute_v1.AccessConfig(
                name="External NAT",
                type_="ONE_TO_ONE_NAT"
            )
        ]
    )

    # Startup script in instance metadata
    metadata = compute_v1.Metadata(
        items=[
            compute_v1.Items(
                key="startup-script",
                value=STARTUP_SCRIPT
            )
        ]
    )

    # Assemble the instance configuration
    # Network tag is intentionally applied later using setTags.
    instance = compute_v1.Instance(
        name=INSTANCE_NAME,
        machine_type=f"zones/{ZONE}/machineTypes/{MACHINE_TYPE}",
        disks=[disk],
        network_interfaces=[network_interface],
        metadata=metadata
    )

    print(f"Creating VM instance '{INSTANCE_NAME}' in zone {ZONE}...")

    op = instance_client.insert(
        project=project,
        zone=ZONE,
        instance_resource=instance
    )

    op.result()

    print(f"Instance '{INSTANCE_NAME}' created.")

    # Get the newly created instance so we can obtain its tag fingerprint
    created_instance = instance_client.get(
        project=project,
        zone=ZONE,
        instance=INSTANCE_NAME
    )

    # Apply the allow-5000 network tag using setTags
    tags_resource = compute_v1.Tags(
        items=[TAG],
        fingerprint=created_instance.tags.fingerprint
    )

    tag_op = instance_client.set_tags(
        project=project,
        zone=ZONE,
        instance=INSTANCE_NAME,
        tags_resource=tags_resource
    )

    tag_op.result()

    print(f"Network tag '{TAG}' applied to instance.")


def get_instance_ip():
    """Retrieve and print the VM's external IP address."""

    inst = instance_client.get(
        project=project,
        zone=ZONE,
        instance=INSTANCE_NAME
    )

    ip = inst.network_interfaces[0].access_configs[0].nat_i_p

    print("\n--------------------------------------------------")
    print(f"Flask application address: http://{ip}:5000")
    print("--------------------------------------------------")
    print(
        "Note: The startup script may take 1-2 minutes "
        "to finish setting up Flask."
    )


if __name__ == "__main__":
    create_firewall_rule()
    create_instance()
    get_instance_ip()