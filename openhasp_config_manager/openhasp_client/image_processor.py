from typing import Tuple

from PIL import Image
from temppathlib import NamedTemporaryFile


class OpenHaspImageProcessor:
    async def image_to_rgb565(self, in_image, out_image, size: Tuple[int | None, int | None], fitscreen: bool):
        """
        Transforms an image to rgb565 format according to LVGL requirements.
        :param in_image: the image to transform
        :param out_image: the output file
        :param size: the size of the output image
        :param fitscreen: if True, the image will be resized to fit the screen
        """
        import struct

        if in_image.startswith("http"):
            tmp_file_container = await self._fetch_image_from_url(in_image)
        else:
            # copy file to temp file
            tmp_file_container = NamedTemporaryFile(delete=False)
            import shutil

            shutil.copy(in_image, tmp_file_container.path)

        try:
            def _process_image():
                im = Image.open(tmp_file_container.file)
                original_width, original_height = im.size
                width, height = size

                if not fitscreen:
                    valid_w: list[int] = []
                    for x in (width, original_width):
                        if x is not None and x > 0:
                            valid_w.append(x)
                    w = min(valid_w) if valid_w else original_width
                    
                    valid_h: list[int] = []
                    for x in (height, original_height):
                        if x is not None and x > 0:
                            valid_h.append(x)
                    h = min(valid_h) if valid_h else original_height
                    
                    im.thumbnail((int(h), int(w)), Image.Resampling.LANCZOS)
                else:
                    h_val = height if height is not None else original_height
                    w_val = width if width is not None else original_width
                    im = im.resize((int(h_val), int(w_val)), Image.Resampling.LANCZOS)
                w, h = im.size  # actual size after resize

                out_image.write(struct.pack("I", h << 21 | w << 10 | 4))

                img = im.convert("RGB")
                for pix in img.getdata():
                    r = (pix[0] >> 3) & 0x1F
                    g = (pix[1] >> 2) & 0x3F
                    b = (pix[2] >> 3) & 0x1F
                    out_image.write(struct.pack("H", (r << 11) | (g << 5) | b))
                out_image.flush()

                im.close()
                img.close()

            import asyncio
            await asyncio.to_thread(_process_image)
        finally:
            tmp_file_container.path.unlink()

    @staticmethod
    async def _fetch_image_from_url(in_image) -> NamedTemporaryFile:
        import aiohttp

        # consider last part of the url as filename
        filename = in_image.split("/")[-1]
        # remove url args, if any
        filename = filename.split("?")[0]
        
        async with aiohttp.ClientSession() as session:
            async with session.get(in_image) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", None)
                content = await response.read()

        # add file extension based on content type
        from mimetypes import guess_extension

        guess = guess_extension(content_type)
        if guess is not None:
            filename = filename + guess

        tmp_image = NamedTemporaryFile(suffix=filename, delete=False)
        tmp_image.file.write(content)
        return tmp_image
