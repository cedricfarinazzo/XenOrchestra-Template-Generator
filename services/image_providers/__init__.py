from .base import BaseImageProvider
from .debian import DebianImageProvider
from .ubuntu import UbuntuImageProvider

IMAGE_PROVIDERS: dict[str, BaseImageProvider] = {
    "debian": DebianImageProvider,
    "ubuntu": UbuntuImageProvider,
}
