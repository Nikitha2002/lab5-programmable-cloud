#!/usr/bin/env python3
import time
from google.cloud import compute_v1

# Configuration
PROJECT = "lab5-programmable-cloud-510117"
ZONE = "us-central1-a"
SOURCE_INSTANCE = "flask-vm"
IMAGE_NAME = "flask-image"
NUM_INSTANCES = 3
MACHINE_TYPE = "e2-micro"

instances_client = compute_v1.InstancesClient()
images_client = compute_v1.ImagesClient()
global_operations_client = compute_v1.GlobalOperationsClient()


def stop_source_instance():
    """Stops the source VM instance before creating an image."""
    print(f"Stopping instance '{SOURCE_INSTANCE}'...")
    try:
        op = instances_client.stop(project=PROJECT, zone=ZONE, instance=SOURCE_INSTANCE)
        op.result()
        print(f"Instance '{SOURCE_INSTANCE}' stopped successfully.")
    except Exception as e:
        print(f"Note on stopping instance: {e}")


def create_image_from_instance():
    """Creates a custom disk image from the boot disk of the source VM."""
    print(f"Creating image '{IMAGE_NAME}' from instance '{SOURCE_INSTANCE}'...")
    
    # Get boot disk URI of flask-vm
    instance = instances_client.get(project=PROJECT, zone=ZONE, instance=SOURCE_INSTANCE)
    boot_disk_source = instance.disks[0].source

    image = compute_v1.Image(
        name=IMAGE_NAME,
        source_disk=boot_disk_source
    )
    
    op = images_client.insert(project=PROJECT, image_resource=image)
    op.result()
    print(f"Custom image '{IMAGE_NAME}' created successfully.")


def create_instance_from_image(instance_name):
    """Creates a new instance using the custom image as the boot disk."""
    print(f"Starting creation of '{instance_name}'...")
    start_time = time.time()

    # Configure boot disk from custom image
    initialize_params = compute_v1.AttachedDiskInitializeParams(
        source_image=f"projects/{PROJECT}/global/images/{IMAGE_NAME}"
    )
    boot_disk = compute_v1.AttachedDisk(
        boot=True,
        auto_delete=True,
        initialize_params=initialize_params
    )

    # Network interface with ephemeral public IP
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

    op = instances_client.insert(project=PROJECT, zone=ZONE, instance_resource=instance)
    op.result()

    elapsed_time = time.time() - start_time
    print(f"Instance '{instance_name}' created in {elapsed_time:.2f} seconds.")
    return elapsed_time


def main():
    # 1. Stop the original VM
    stop_source_instance()

    # 2. Create image from original VM
    create_image_from_instance()

    # 3. Spin up 3 new instances from the image and measure boot times
    timings = []
    for i in range(1, NUM_INSTANCES + 1):
        vm_name = f"flask-vm-replica-{i}"
        elapsed = create_instance_from_image(vm_name)
        timings.append((vm_name, elapsed))

    # Summary
    print("\n--- Summary of Creation Times ---")
    for vm_name, elapsed in timings:
        print(f"{vm_name}: {elapsed:.2f} seconds")


if __name__ == "__main__":
    main()