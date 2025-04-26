from typing import Tuple


class OpenHaspImageProcessor:

    @staticmethod
    def image_to_rgb565(in_image, out_image, size: Tuple[int or None, int or None], fitscreen: bool):
        """
        Transforms an image to rgb565 format according to LVGL requirements.
        :param in_image: the image to transform
        :param out_image: the output file
        :param size: the size of the output image
        :param fitscreen: if True, the image will be resized to fit the screen
        """
        import requests
        import struct
        from PIL import Image

        if in_image.startswith("http"):

            # consider last part of the url as filename
            filename = in_image.split("/")[-1]
            # remove url args, if any
            filename = filename.split("?")[0]
            import temppathlib
            with temppathlib.NamedTemporaryFile(suffix=filename) as tmp_image:
                response = requests.get(in_image, stream=True)
                response.raise_for_status()
                content = response.content
                tmp_image.file.write(content)
                im = Image.open(tmp_image.path)
        else:
            im = Image.open(in_image)

        original_width, original_height = im.size
        width, height = size

        if not fitscreen:
            width = min(w for w in [width, original_width] if w is not None and w > 0)
            height = min(h for h in [height, original_height] if h is not None and h > 0)
            im.thumbnail((height, width), Image.Resampling.LANCZOS)
        else:
            im = im.resize((height, width), Image.Resampling.LANCZOS)
        width, height = im.size  # actual size after resize

        out_image.write(struct.pack("I", height << 21 | width << 10 | 4))

        img = im.convert("RGB")
        for pix in img.getdata():
            r = (pix[0] >> 3) & 0x1F
            g = (pix[1] >> 2) & 0x3F
            b = (pix[2] >> 3) & 0x1F
            out_image.write(struct.pack("H", (r << 11) | (g << 5) | b))
        out_image.flush()

        im.close()
        img.close()
