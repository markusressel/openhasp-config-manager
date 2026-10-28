import asyncio
import logging
from collections import defaultdict

from openhasp_config_manager.haad.objects import ObjectController
from openhasp_config_manager.openhasp_client.image_server import ImageServer

import os
from typing import Optional, Tuple

# TODO: make this configurable via config file or env variable, using container_app_conf
OPENHASP_IMAGE_PORT = int(os.environ.get("OPENHASP_IMAGE_PORT", "0"))
OPENHASP_IMAGE_HOST = os.environ.get("OPENHASP_IMAGE_HOST", None)

plate_locks = defaultdict(asyncio.Lock)
_global_image_server = ImageServer(listen_host="0.0.0.0", listen_port=OPENHASP_IMAGE_PORT)
_server_lock = asyncio.Lock()

import socket


def get_local_ip() -> str:
    """
    Dynamically determines the host's primary outbound local IP address.

    This works by creating a UDP socket and connecting to a dummy external IP.
    It doesn't actually send any packets; instead, it asks the OS networking stack:
    'If I were to send a packet out to the local subnet/internet, which local IP
    interface would the routing table choose?'

    This reliably ignores Docker bridges, loopbacks, and virtual interfaces,
    and accurately grabs the primary LAN IP.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class ImageObjectController(ObjectController):
    """
    Controller for an image object on the OpenHASP plate.
    """

    OBJ_TYPE = "img"

    LOGGER = logging.getLogger(__name__)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # the `src` the plate was configured with, see `restore_default_source`
        self._default_source: Optional[str] = None
        self._default_source_read = False
        # the `w` and `h` the plate was configured with, see `push_image`
        self._size: Optional[Tuple[int, int]] = None

    async def init(self):
        """
        Sets up the image object. This is called when the page is loaded, and can be used to set up the initial state of the object.

        See: https://www.openhasp.com/0.7.0/design/objects/image/
        """
        self.LOGGER.debug(f"Initializing image object {self.object_id}")

    async def push_image(self, image: str, width: Optional[int] = None, height: Optional[int] = None):
        """
        Pushes an image to this image object. The image is resized to the given size, keeping its aspect ratio.

        :param image: the image to set, can be a URL or anything that can be opened by PIL.Image.open, f.ex. a file path
        :param width: the width of the image in pixels, the `w` of the object on the plate (its JSONL object) if not given
        :param height: the height of the image in pixels, the `h` of the object on the plate if not given
        """
        try:
            if width is None or height is None:
                object_width, object_height = await self._read_size()
                width = object_width if width is None else width
                height = object_height if height is None else height

            # before the first push replaces it
            await self._read_default_source()

            ip = OPENHASP_IMAGE_HOST or get_local_ip()

            async with _server_lock:
                if not _global_image_server._is_running:
                    _global_image_server.access_host = ip
                    await _global_image_server.start()

            plate_id = self.client._device.name
            async with plate_locks[plate_id]:
                await self.client.set_image(
                    obj=self.object_id,
                    image=image,
                    access_host=ip,
                    access_port=_global_image_server.listen_port,
                    size=(width, height),
                    image_server=_global_image_server,
                    timeout=5,
                )
        except Exception as e:
            self.LOGGER.error(f"Error pushing image: {e}")

    async def _read_size(self) -> Tuple[int, int]:
        """:return: the `w` and `h` of the object on the plate, which is asked once. :raises ValueError: if it doesn't know them"""
        if self._size is None:
            size = [await self.client.get_object_property(self.object_id, prop) for prop in ("w", "h")]
            try:
                self._size = (int(size[0]), int(size[1]))
            except (TypeError, ValueError):
                raise ValueError(f"The plate did not report the size of {self.object_id}: {size}")
        return self._size

    async def restore_default_source(self) -> bool:
        """
        Shows the image the object was configured with (the `src` of its JSONL object, e.g. a placeholder) again, after
        `push_image` replaced it. The plate is asked for it once, before the first push.

        :return: whether the object has a default image. If not, nothing is sent: hide the object instead.
        """
        source = await self._read_default_source()
        if not source:
            return False
        await self.set_object_properties({"src": source}, force=True)
        return True

    async def _read_default_source(self) -> Optional[str]:
        if not self._default_source_read:
            self._default_source_read = True
            source = await self.client.get_object_property(self.object_id, "src")
            # an image from an earlier run of haad is still on the plate, and was not configured
            if isinstance(source, str) and not source.startswith("http"):
                self._default_source = source
        return self._default_source

    async def set_offset(self, offset_x: int = 0, offset_y: int = 0):
        """
        Sets the offset for this image object
        :param offset_x: the x offset to set in pixels
        :param offset_y: the y offset to set in pixels
        """
        return await self.set_object_properties(
            properties={
                "offset_x": offset_x,
                "offset_y": offset_y,
            }
        )

    async def set_zoom(self, zoom: int = 256):
        """
        Sets the zoom for this image object
        :param zoom: the zoom to set in pixels
        """
        return await self.set_object_properties(
            properties={
                "zoom": zoom,
            }
        )

    async def set_angle(self, angle: int = 0):
        """
        Sets the angle for this image object.
        Rotate the picture around its pivot point. Angle has 0.1 degree precision, so for 45.8° use 458.
        :param angle: the angle to set in degrees
        """
        return await self.set_object_properties(
            properties={
                "angle": angle,
            }
        )

    async def set_pivot(self, pivot_x: int = 0, pivot_y: int = 0):
        """
        Sets the pivot point for this image object.
        By default centered.
        :param pivot_x: the x pivot point to set in pixels
        :param pivot_y: the y pivot point to set in pixels
        """
        return await self.set_object_properties(
            properties={
                "pivot_x": pivot_x,
                "pivot_y": pivot_y,
            }
        )

    async def set_antialiasing(self, antialiasing: bool = False):
        """
        Sets the antialiasing for this image object.
        :param antialiasing: True if antialiasing is enabled, False if it is disabled.
        """
        return await self.set_object_properties(
            properties={
                "antialias": antialiasing,
            }
        )
