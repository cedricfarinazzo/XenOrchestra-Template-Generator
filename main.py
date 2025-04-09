from pathlib import Path
import os
import time
import asyncio

from services.debian_cloud_image import DebianCloudImage
from services.xen_orchestra import XenOrchestraApi

async def main():

    debian_cloud_dl = DebianCloudImage(version="12")
    
    dl_folder = Path("/tmp")
    dl_format = "vmdk"

    if (dl_folder / debian_cloud_dl.get_image_name().replace(".qcow2", f".{dl_format}")).exists():
        image_path = dl_folder / debian_cloud_dl.get_image_name().replace(".qcow2", f".{dl_format}")
    else:
        image_path = debian_cloud_dl.download_and_convert_image_to_format(
            folder_out=dl_folder,
            format="vmdk"
        )

    host = os.getenv("XOA_URL")
    auth_token = os.getenv("XOA_TOKEN")

    api = XenOrchestraApi(
        host=host,
        auth_token=auth_token
    )
    print("Connecting to Xen Orchestra...")
    await api.connect()
    print("Connected to Xen Orchestra.")
    print("Logging in...")
    await api.login()
    print("Logged in.")


    print()
    print()

    sr_id = await api.get_sr_by_name("Local storage - srv3")
    print(f"SR ID: {sr_id}")

    file_format = image_path.suffix[1:]
    print(f"Image format: {file_format}")

    build_id = int(time.time())
    upload_file_name = f"{image_path.stem}.{build_id}.{file_format}"
    print(f"Upload file name: {upload_file_name}")

    # Get the size of the image using pathlib
    image_size = image_path.stat().st_size
    print(f"Image size: {image_size} bytes")

    vdi_id = api.import_disk(
        sr_id=sr_id,
        file_path=image_path,
        upload_name=upload_file_name,
    )
    print(f"VDI ID: {vdi_id}")

    default_debian12_template_id = await api.get_template_by_name("Debian Bookworm 12")
    print(f"Template ID: {default_debian12_template_id}")

    eth1_network_id = await api.get_network_by_name("Pool-wide network associated with eth1")
    print(f"Network ID: {eth1_network_id}")

    print()
    print()

    vm_id = await api.create_vm(
        name_label=f"template.{image_path.stem}.{build_id}",
        name_description=f"Debian 12 GenericCloud amd64 {build_id} template",
        template_id=default_debian12_template_id,
        network_id=eth1_network_id,
        cpus=1,
        memory=1,
        tags=[f"template.{image_path.stem}"]
    )
    print(f"VM ID: {vm_id}")

    print()
    print("Attaching VDI to VM...")
    attach_disk_response = await api.attack_vdi_to_vm(
        vm_id=vm_id,
        vdi_id=vdi_id,
    )
    print(f"VDI attached to VM: {attach_disk_response}")

    print()
    print("Set boot order...")
    boot_order_response = await api.set_boot_order(
        vm_id=vm_id,
        boot_order="cd",
    )
    print(f"Boot order set: {boot_order_response}")

    print()

    print("Converting VM to template...")
    convert_response = await api.convert_vm_to_template(
        vm_id=vm_id,
    )
    print(f"VM converted to template: {convert_response}")

    await api.disconnect()
    print("Disconnected.")

asyncio.get_event_loop().run_until_complete(main())