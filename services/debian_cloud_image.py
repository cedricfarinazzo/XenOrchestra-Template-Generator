from pathlib import Path
import subprocess
import requests

DEBIAN_CLOUD_IMAGE_URL = "https://cdimage.debian.org/images/cloud"

class DebianCloudImage:
    def __init__(
        self,
        version: str,
        arch: str = "amd64",
        variant: str = "genericcloud"
    ):
        self.version = version
        self.arch = arch
        self.variant = variant
    
    def get_version_name(self):
        match self.version:
            case "12":
                return "bookworm"
            case "11":
                return "bullseye"
            case "10":
                return "buster"
            case "9":
                return "stretch"
            case "8":
                return "jessie"
            case "7":
                return "wheezy"
            case _:
                raise ValueError(f"Unsupported Debian version: {self.version}")

    def get_image_name(self):
        return f"debian-{self.version}-{self.variant}-{self.arch}.qcow2"
    
    def get_image_url(self):
        version_name = self.get_version_name()
        image_name = self.get_image_name()
        return f"{DEBIAN_CLOUD_IMAGE_URL}/{version_name}/latest/{image_name}"

    def download_image(self, folder_out: Path) -> Path:
        image_path = folder_out / self.get_image_name()

        url = self.get_image_url()
        response = requests.get(url, stream=True)
        
        if response.status_code == 200:
            with image_path.open('wb+') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            return image_path
        else:
            raise Exception(f"Failed to download image from {url}. Status code: {response.status_code}")

    def download_and_convert_image_to_format(self, folder_out: Path, format: str = "qcow2") -> Path:
        image_path = self.download_image(folder_out)
        converted_image_path = image_path.with_suffix(f".{format}")
        
        if image_path == converted_image_path:
            # No conversion needed, return the original image path
            return image_path
        
        # Convert to the desired format using qemu-img
        ret = subprocess.run(
            [
                "qemu-img", "convert",
                "-f", image_path.suffix[1:],
                "-O", converted_image_path.suffix[1:],
                str(image_path),
                str(converted_image_path)
            ]
            , check=True
        )
        
        if ret.returncode != 0:
            print("Conversion failed")
            print(f"Command: {' '.join(ret.args)}")
            print(f"Return code: {ret.returncode}")
            print("Error output:")
            if ret.stdout:
                print(ret.stdout)
            if ret.stderr:
                print(ret.stderr)
            
            raise Exception("Image conversion failed")

        # Remove the original image file
        image_path.unlink()
        
        return converted_image_path