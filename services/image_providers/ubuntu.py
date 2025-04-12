from typing import Literal, Optional, Callable
from pathlib import Path
from pydantic import BaseModel
import requests

from ..tools import logger

from .base import BaseImageProvider, IMAGE_OUTPUT_DIR

UBUNTU_IMAGE_URL = "https://releases.ubuntu.com"


class UbuntuImageConfig(BaseModel):
    version: str
    arch: Literal["amd64", "arm64"] = "amd64"
    variant: str = "genericcloud"

class UbuntuImageProvider(BaseImageProvider):
    """
    Ubuntu image provider.
    """

    def __init__(
        self,
        version: str,
        arch: str = "amd64",
        variant: str = "live-server"
    ):
        super().__init__(version, arch)
        # Validate the config with Pydantic
        self.config = UbuntuImageConfig(
            version=version,
            arch=arch,
            variant=variant
        )


    def __get_image_name(self) -> str:
        return f"ubuntu-{self.config.version}-{self.config.variant}-{self.config.arch}.iso"
    
    def __get_image_url(self) -> str:
        image_name = self.__get_image_name()
        return f"{UBUNTU_IMAGE_URL}/{self.config.version}/{image_name}"

    def __download(
        self,
        image_output_path: Path,
        use_cache: bool = True,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Path:
        """
        Download the image in qcow2 format.
        Args:
            image_output_path: Path to save the downloaded image.
            use_cache: If True, use cached image if available.
            progress_callback: Optional callback function to report progress (0.0 to 1.0).
        """
        # Default no-op progress callback
        if progress_callback is None:
            progress_callback = lambda _: None

        progress_callback(0.0)

        # Check if the image already exists
        if use_cache and image_output_path.exists():
            logger.info(f"Image already exists: {image_output_path}")
            # Report 100% progress
            progress_callback(1.0)
            # Return the existing image path
            return image_output_path
        
        # Download the image
        image_url = self.__get_image_url()
        logger.info(f"Downloading image from {image_url} to {image_output_path}")
        response = requests.get(image_url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0
        with image_output_path.open('wb+') as file:
            for data in response.iter_content(chunk_size=8192):
                file.write(data)
                downloaded_size += len(data)
                # Report progress
                progress_callback(downloaded_size / total_size)
        logger.info(f"Downloaded image to {image_output_path}")
        # Report 100% progress
        progress_callback(1.0)

        return image_output_path

    def download_image(self, use_cache = True, progress_callback = None):
        """
        Download the image with progress reporting.
        Args:
            use_cache: If True, use cached image if available.
            progress_callback: Optional callback function to report progress (0.0 to 1.0).
        Returns:
            Path to the downloaded image in ISO format.
        """
        # Define the output path for the qcow2 image
        image_iso_path = IMAGE_OUTPUT_DIR / self.__get_image_name()

        # Download the image
        self.__download(image_iso_path, use_cache, progress_callback)

        return image_iso_path