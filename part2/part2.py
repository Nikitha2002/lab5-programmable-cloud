#!/usr/bin/env python3

import time
from google.cloud import compute_v1


# Configuration
PROJECT = "lab5-programmable-cloud-510117"
ZONE = "us-central1-a"
SOURCE_INSTANCE = "flask-vm"
SNAPSHOT_NAME = "base-snapshot-flask-vm"
NUM_INSTANCES = 3
MACHINE_TYPE = "f1-micro"


instances_client = compute_v1.InstancesClient()
disks_client = compute_v1.DisksClient()


def stop_source_instance():
    """Stops the source VM instance before creating a snapshot."""

    print(f"Stopping instance '{SOURCE_INSTANCE}'...")

    try:
        op = instances_client.stop(
            project=PROJECT,
            zone=ZONE,
            instance=SOURCE_INSTANCE
        )
        op.result()
        print(f"Instance '{SOURCE_INSTANCE}' stopped successfully.")

    except Exception as e:
        print(f"Note on stopping instance: {e}")


def create_snapshot_from_instance():
    """Creates a snapshot from the boot disk of the source VM."""

    print(
        f"Creating snapshot '{SNAPSHOT_NAME}' "
        f"from instance '{SOURCE_INSTANCE}'..."
    )

    instance = instances_client.get(
        project=PROJECT,
        zone=ZONE,
        instance=SOURCE_INSTANCE
    )

    boot_disk_source = instance.disks[0].source
    boot_disk_name = boot_disk_source.split("/")[-1]

    snapshot = compute_v1.Snapshot(
        name=SNAPSHOT_NAME,
        source_disk=(
            f"projects/{PROJECT}/zones/{ZONE}/disks/{boot_disk_name}"
        )
    )

    op = disks_client.create_snapshot(
        project=PROJECT,
        zone=ZONE,
        disk=boot_disk_name,
        snapshot_resource=snapshot
    )

    op.result()

    print(f"Snapshot '{SNAPSHOT_NAME}' created successfully.")


def create_instance_from_snapshot(instance_name):
    """Creates a new VM using the snapshot as its boot disk."""

    print(f"Starting creation of '{instance_name}'...")
    start_time = time.time()

    initialize_params = compute_v1.AttachedDiskInitializeParams(
        source_snapshot=(
            f"projects/{PROJECT}/global/snapshots/{SNAPSHOT_NAME}"
        )
    )

    boot_disk = compute_v1.AttachedDisk(
        boot=True,
        auto_delete=True,
        initialize_params=initialize_params
    )

    access_config = compute_v1.AccessConfig(
        type_=compute_v1.AccessConfig.Type.ONE_TO_ONE_NAT.name,
        name="External NAT"
    )

    network_interface = compute_v1.NetworkInterface(
        network="global/networks/default",
        access_configs=[access_config]
    )

    instance = compute_v1.Instance(
        name=instance_name,
        machine_type=f"zones/{ZONE}/machineTypes/{MACHINE_TYPE}",
        disks=[boot_disk],
        network_interfaces=[network_interface],
        tags=compute_v1.Tags(items=["allow-5000"])
    )

    op = instances_client.insert(
        project=PROJECT,
        zone=ZONE,
        instance_resource=instance
    )

    op.result()

    elapsed_time = time.time() - start_time

    print(
        f"Instance '{instance_name}' created "
        f"in {elapsed_time:.2f} seconds."
    )

    return elapsed_time


def main():
    # 1. Stop the original VM
    stop_source_instance()

    # 2. Create a snapshot from the original VM's boot disk
    create_snapshot_from_instance()

    # 3. Create three instances from the snapshot
    timings = []

    for i in range(1, NUM_INSTANCES + 1):
        vm_name = f"flask-vm-replica-{i}"

        elapsed = create_instance_from_snapshot(vm_name)

        timings.append((vm_name, elapsed))

    # 4. Print timing summary
    print("\n--- Summary of Creation Times ---")

    for vm_name, elapsed in timings:
        print(f"{vm_name}: {elapsed:.2f} seconds")


if __name__ == "__main__":
    main()