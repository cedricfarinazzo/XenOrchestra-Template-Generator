from io import BufferedReader, RawIOBase
from typing import Callable, Optional


class BufferedReaderWithProgressCallback(BufferedReader):
    """
    A BufferedReader that provides a callback for progress updates.
    This class wraps a raw IO object and allows for progress tracking
    while reading data from it.
    """

    def __init__(
        self,
        raw: RawIOBase,
        buffer_size: int = 8192,
        progress_callback: Optional[Callable[[float], None]] = None,
    ):
        super().__init__(raw, buffer_size)
        self.progress_callback = progress_callback
        self.total_size = float(self.get_file_size())
        self.bytes_read = 0

    def get_file_size(self) -> int:
        # Move to the end of the file to get its size
        current_position = self.tell()
        # Seek to the end
        self.raw.seek(0, 2)
        # Get the size
        size = self.raw.tell()
        # Move back to the original position
        self.raw.seek(current_position)
        return size

    def read(self, size: Optional[int] = -1) -> bytes:
        data = super().read(size)
        self.bytes_read += len(data)

        if self.progress_callback:
            self.progress_callback(float(self.bytes_read) / self.total_size)

        return data
