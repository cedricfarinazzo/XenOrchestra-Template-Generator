from pathlib import Path
from services.debian_cloud_image import DebianCloudImage

d = DebianCloudImage(version="12")

d.download_and_convert_image_to_format(
    folder_out=Path("/tmp"),
    format="vmdk"
)