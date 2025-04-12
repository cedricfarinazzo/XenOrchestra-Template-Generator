from enum import Enum
from typing import Literal, Optional, Callable
from pathlib import Path
from pydantic import BaseModel, field_validator
import requests
import subprocess

from ..utils import logger

from .base import BaseImageProvider, IMAGE_OUTPUT_DIR

DEBIAN_CLOUD_IMAGE_URL = "https://cdimage.debian.org/images/cloud"

class DebianVersion(str, Enum):
    BOOKWORM = "12"
    BULLSEYE = "11"
    BUSTER = "10"
    STRETCH = "9"
    JESSIE = "8"
    WHEEZY = "7"

class DebianVersionName(str, Enum):
    BOOKWORM = "bookworm"
    BULLSEYE = "bullseye"
    BUSTER = "buster"
    STRETCH = "stretch"
    JESSIE = "jessie"
    WHEEZY = "wheezy"

# Version name mapping
VERSION_TO_NAME = {
    DebianVersion.BOOKWORM: DebianVersionName.BOOKWORM,
    DebianVersion.BULLSEYE: DebianVersionName.BULLSEYE,
    DebianVersion.BUSTER: DebianVersionName.BUSTER, 
    DebianVersion.STRETCH: DebianVersionName.STRETCH,
    DebianVersion.JESSIE: DebianVersionName.JESSIE,
    DebianVersion.WHEEZY: DebianVersionName.WHEEZY,
}

class DebianImageConfig(BaseModel):
    version: str
    arch: Literal["amd64", "arm64"] = "amd64"
    variant: str = "genericcloud"
    
    @field_validator('version')
    def validate_version(cls, v):
        if v not in VERSION_TO_NAME:
            valid_versions = ", ".join(VERSION_TO_NAME.keys())
            raise ValueError(f"Unsupported Debian version: {v}. Valid versions are: {valid_versions}")
        return v
    
    @field_validator('arch')
    def validate_architecture(cls, v):
        return v.lower()

class DebianImageProvider(BaseImageProvider):
    """
    Debian image provider.
    """

    def __init__(
        self,
        version: str,
        arch: str = "amd64",
        variant: str = "genericcloud"
    ):
        super().__init__(version, arch)
        # Validate the config with Pydantic
        self.config = DebianImageConfig(
            version=version,
            arch=arch,
            variant=variant
        )

    def __get_version_name(self) -> str:
        return VERSION_TO_NAME[self.config.version].value

    def __get_image_name(self) -> str:
        return f"debian-{self.config.version}-{self.config.variant}-{self.config.arch}.qcow2"
    
    def __get_image_url(self) -> str:
        version_name = self.__get_version_name()
        image_name = self.__get_image_name()
        return f"{DEBIAN_CLOUD_IMAGE_URL}/{version_name}/latest/{image_name}"

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

    def __convert_image(
        self,
        image_qcow2_path: Path,
        use_cache: bool = True,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Path:
        """
        Convert the downloaded image to VMDK format.
        Args:
            image_qcow2_path: Path to the downloaded qcow2 image.
        Returns:
            Path to the converted VMDK image.
        """
        image_vmdk_path = image_qcow2_path.with_suffix(".vmdk")

        logger.info(f"Converting image to VMDK format: {image_vmdk_path}")

        # Check if the VMDK image already exists
        if use_cache and image_vmdk_path.exists():
            logger.info(f"VMDK image already exists: {image_vmdk_path}")
            return image_vmdk_path    
    
        # Use qemu-img to convert the image
        subprocess.run(["qemu-img", "convert", "-O", "vmdk", str(image_qcow2_path), str(image_vmdk_path)], check=True)
        logger.info(f"Converted image to VMDK format: {image_vmdk_path}")
        return image_vmdk_path

    def download_image(self, use_cache = True, progress_callback = None):
        """
        Download the image with progress reporting.
        Args:
            use_cache: If True, use cached image if available.
            progress_callback: Optional callback function to report progress (0.0 to 1.0).
        Returns:
            Path to the downloaded image in VMDK format.
        """
        # Define the output path for the qcow2 image
        image_qcow2_path = IMAGE_OUTPUT_DIR / self.__get_image_name()

        # Download the image
        self.__download(image_qcow2_path, use_cache, progress_callback)

        # Convert to VMDK format
        image_vmdk_path = self.__convert_image(image_qcow2_path, use_cache, progress_callback)

        return image_vmdk_path