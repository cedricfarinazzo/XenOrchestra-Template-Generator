from abc import ABC
from pathlib import Path
from typing import Callable, Optional

IMAGE_OUTPUT_DIR = Path(__file__).parent / "images"

class BaseImageProvider(ABC):
    """
    Base class for image providers.
    """

    def __init__(
        self,
        version: str,
        arch: str = "amd64",
    ):
        self.version = version
        self.arch = arch


    def download_image(
        self,
        use_cache: bool = True,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Path:
        """
        Download the image with progress reporting.

        Args:
            use_cache: If True, use cached image if available.
            progress_callback: Optional callback function to report progress (0.0 to 1.0).

        Returns:
            Path to the downloaded image in VMDK format or ISO format.
        """
        raise NotImplementedError("Subclasses must implement this method.")