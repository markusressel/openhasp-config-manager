import asyncio

from openhasp_config_manager.ad.objects import ObjectController

lock = asyncio.Lock()


class ImageObjectController(ObjectController):
    """
    Controller for an image object on the OpenHASP plate.
    """

    async def init(self):
        """
        Sets up the image object. This is called when the page is loaded, and can be used to set up the initial state of the object.

        See: https://www.openhasp.com/0.7.0/design/objects/image/
        """
        self.app.log(f"Initializing image object {self.object_id}", level="DEBUG")

    async def push_image(self, image: str, width: int, height: int):
        """
        Pushes an image to this image object. The image must be a base64 encoded string, and the width and height must be specified in pixels.

        :param image: the image to set, can be a URL or anything that can be opened by PIL.Image.open, f.ex. a file path
        :param width: the width of the image in pixels
        :param height: the height of the image in pixels
        """
        try:
            async with lock:
                await self.client.set_image(
                    obj=self.object_id,
                    image=image,
                    size=(width, height),
                    listen_host="0.0.0.0",
                    listen_port=20000,
                    access_host="192.168.2.129",
                    access_port=20000,
                    timeout=3,
                )
        except Exception as e:
            self.app.log(f"Error pushing image: {e}", level="ERROR")

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
