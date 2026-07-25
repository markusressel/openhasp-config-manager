import asyncio
from collections import defaultdict

from openhasp_config_manager.haad.objects import ObjectController
from openhasp_config_manager.openhasp_client.image_server import ImageServer

plate_locks = defaultdict(asyncio.Lock)
_global_image_server = ImageServer(listen_host="0.0.0.0", listen_port=0)
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
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

class ImageObjectController(ObjectController):
    """
    Controller for an image object on the OpenHASP plate.
    """

    async def init(self):
        """
        Sets up the image object. This is called when the page is loaded, and can be used to set up the initial state of the object.

        See: https://www.openhasp.com/0.7.0/design/objects/image/
        """
        self.controller.log(f"Initializing image object {self.object_id}", level="DEBUG")

    async def push_image(self, image: str, width: int, height: int):
        """
        Pushes an image to this image object. The image must be a base64 encoded string, and the width and height must be specified in pixels.

        :param image: the image to set, can be a URL or anything that can be opened by PIL.Image.open, f.ex. a file path
        :param width: the width of the image in pixels
        :param height: the height of the image in pixels
        """
        try:
            ip = get_local_ip()
            
            async with _server_lock:
                if not _global_image_server._is_running:
                    _global_image_server.access_host = ip
                    await _global_image_server.start()
                
            plate_id = self.client._device.name
            async with plate_locks[plate_id]:
                await self.client.set_image(
                    obj=self.object_id,
                    image=image,
                    size=(width, height),
                    image_server=_global_image_server,
                    timeout=5,
                )
        except Exception as e:
            self.controller.log(f"Error pushing image: {e}", level="ERROR")

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
