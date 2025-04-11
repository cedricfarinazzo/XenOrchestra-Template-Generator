from pathlib import Path
import subprocess
import requests
import tqdm
from enum import Enum
from typing import Dict, Optional, Literal, Callable
from pydantic import BaseModel, Field, validator

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

class ImageFormat(str, Enum):
    QCOW2 = "qcow2"
    VMDK = "vmdk"
    VHD = "vhd"
    RAW = "raw"

class DebianImageConfig(BaseModel):
    version: str
    arch: Literal["amd64", "arm64"] = "amd64"
    variant: str = "genericcloud"
    
    @validator('version')
    def validate_version(cls, v):
        if v not in VERSION_TO_NAME:
            valid_versions = ", ".join(VERSION_TO_NAME.keys())
            raise ValueError(f"Unsupported Debian version: {v}. Valid versions are: {valid_versions}")
        return v
    
    @validator('arch')
    def validate_architecture(cls, v):
        return v.lower()


class DebianCloudImage:
    def __init__(
        self,
        version: str,
        arch: str = "amd64",
        variant: str = "genericcloud"
    ) -> None:
        # Validate the config with Pydantic
        self.config = DebianImageConfig(
            version=version,
            arch=arch,
            variant=variant
        )
    
    def get_version_name(self) -> str:
        return VERSION_TO_NAME[self.config.version].value

    def get_image_name(self) -> str:
        return f"debian-{self.config.version}-{self.config.variant}-{self.config.arch}.qcow2"
    
    def get_image_url(self) -> str:
        version_name = self.get_version_name()
        image_name = self.get_image_name()
        return f"{DEBIAN_CLOUD_IMAGE_URL}/{version_name}/latest/{image_name}"

    def download_image(self, folder_out: Path, progress_callback: Optional[Callable[[float], None]] = None) -> Path:
        """Download cloud image with progress reporting.
        
        Args:
            folder_out: Path to download the image to
            progress_callback: Optional callback function to report progress (0.0 to 1.0)
            
        Returns:
            Path to the downloaded image
        """
        # Default no-op progress callback
        if progress_callback is None:
            progress_callback = lambda _: None
            
        image_path = folder_out / self.get_image_name()
        url = self.get_image_url()
        
        # Report initial progress
        progress_callback(0.0)
        
        response = requests.get(url, stream=True)
        
        if response.status_code == 200:
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with image_path.open('wb+') as file:
                with tqdm.tqdm(
                    total=total_size,
                    unit='B',
                    unit_scale=True,
                    desc=f"Downloading {self.get_image_name()}",
                ) as progress_bar:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
                        downloaded_size += len(chunk)
                        progress_bar.update(len(chunk))
                        
                        # Report progress as percentage
                        if total_size > 0:  # Avoid division by zero
                            progress_percentage = min(downloaded_size / total_size, 1.0)
                            progress_callback(progress_percentage)
                        
            # Ensure 100% progress is reported
            progress_callback(1.0)
            return image_path
        else:
            raise Exception(f"Failed to download image from {url}. Status code: {response.status_code}")

    def download_and_convert_image_to_format(
        self, 
        folder_out: Path, 
        format: str = "qcow2",
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Path:
        """Download and convert cloud image with progress reporting.
        
        Args:
            folder_out: Path to download the image to
            format: Format to convert to (qcow2, vmdk, vhd, raw)
            progress_callback: Optional callback function to report progress (0.0 to 1.0)
            
        Returns:
            Path to the converted image
        """
        # Default no-op progress callback
        if progress_callback is None:
            progress_callback = lambda _: None
            
        # Validate format
        try:
            image_format = ImageFormat(format.lower())
        except ValueError:
            valid_formats = ", ".join([f.value for f in ImageFormat])
            raise ValueError(f"Unsupported image format: {format}. Valid formats are: {valid_formats}")
        
        # Download phase (70% of progress)
        def download_progress(p):
            progress_callback(p * 0.7)
            
        image_path = self.download_image(folder_out, download_progress)
        converted_image_path = image_path.with_suffix(f".{image_format.value}")
        
        if image_path == converted_image_path:
            # No conversion needed, return the original image path
            progress_callback(1.0)  # Complete progress
            return image_path
        
        # Report 70% progress at start of conversion
        progress_callback(0.7)
        
        # Convert to the desired format using qemu-img
        try:
            ret = subprocess.run(
                [
                    "qemu-img", "convert",
                    "-f", image_path.suffix[1:],
                    "-O", converted_image_path.suffix[1:],
                    str(image_path),
                    str(converted_image_path)
                ],
                check=True,
                capture_output=True,
                text=True
            )
            
            # Remove the original image file
            image_path.unlink()
            
            # Report 100% progress after conversion complete
            progress_callback(1.0)
            
            return converted_image_path
            
        except subprocess.CalledProcessError as e:
            print("Conversion failed")
            print(f"Command: {' '.join(e.cmd)}")
            print(f"Return code: {e.returncode}")
            print("Error output:")
            if e.stdout:
                print(e.stdout)
            if e.stderr:
                print(e.stderr)
            
            raise Exception(f"Image conversion failed: {e}")