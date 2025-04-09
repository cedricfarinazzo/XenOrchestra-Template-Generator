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

    upload_file_name = f"{image_path.stem}.{time.time()}.{file_format}"
    print(f"Upload file name: {upload_file_name}")

    # Get the size of the image using pathlib
    image_size = image_path.stat().st_size
    print(f"Image size: {image_size} bytes")

    d = api.import_disk(
        sr_id=sr_id,
        file_path=image_path,
        upload_name=upload_file_name,
    )
    print(d)

    print()
    print()

    await api.disconnect()
    print("Disconnected.")

asyncio.get_event_loop().run_until_complete(main())