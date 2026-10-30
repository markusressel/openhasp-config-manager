from enum import StrEnum
from typing import Tuple

from PIL import Image, ImageOps
from temppathlib import NamedTemporaryFile

from openhasp_config_manager.processing.image_conversion import image_to_binary


class ImageFit(StrEnum):
    """
    How an image is made the size of its object, if their aspect ratios differ. The image always gets exactly that size:
    the plate repeats (tiles) an image that is smaller than its object.
    """

    # scaled to cover the object, the middle is kept and the overhanging edges are cut off
    COVER = "cover"
    # scaled to fit into the object as a whole, with black bars at the sides that are left
    CONTAIN = "contain"
    # stretched to the size of the object, distorting it
    FILL = "fill"


class OpenHaspImageProcessor:
    async def image_to_rgb565(
        self,
        in_image,
        out_image,
        size: Tuple[int | None, int | None],
        fitscreen: bool = False,
        fit: ImageFit = ImageFit.COVER,
    ):
        """
        Transforms an image to rgb565 format according to LVGL requirements.
        :param in_image: the image to transform
        :param out_image: the output file
        :param size: the size of the output image (width, height); the size of the image for a side that is None
        :param fitscreen: if True, the image is stretched to `size` (like `ImageFit.FILL`)
        :param fit: how the image is made `size`, if the aspect ratios differ
        """
        if in_image.startswith("http"):
            tmp_file_container = await self._fetch_image_from_url(in_image)
        else:
            # copy file to temp file
            tmp_file_container = NamedTemporaryFile(delete=False)
            import shutil

            shutil.copy(in_image, tmp_file_container.path)

        try:

            def _process_image():
                with Image.open(tmp_file_container.file) as opened:
                    im = opened.convert("RGB")
                original_width, original_height = im.size
                width, height = size
                target = (
                    int(width) if width else original_width,
                    int(height) if height else original_height,
                )
                method = ImageFit.FILL if fitscreen else fit
                if method == ImageFit.COVER:
                    im = ImageOps.fit(im, target, Image.Resampling.LANCZOS)
                elif method == ImageFit.CONTAIN:
                    im = ImageOps.pad(im, target, Image.Resampling.LANCZOS, color=(0, 0, 0))
                else:
                    im = im.resize(target, Image.Resampling.LANCZOS)
                out_image.write(image_to_binary(im, alpha=False))
                out_image.flush()
                im.close()

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
