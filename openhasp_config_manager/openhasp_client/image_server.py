import asyncio
import logging
import os
import uuid

from aiohttp import web


class ImageServer:
    LOGGER = logging.getLogger(__name__)

    def __init__(self, listen_host: str = "0.0.0.0", listen_port: int = 0, access_host: str = None, access_port: int = None):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.access_host = access_host
        self.access_port = access_port
        self.app = web.Application()
        self.app.router.add_route("GET", "/{image_id}", self._serve_file)
        self.images = {}  # image_id -> (file_path, delete_on_serve, future)
        self.runner = None
        self.site = None
        self.port = listen_port
        self._is_running = False

    async def start(self):
        if self._is_running:
            return
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.listen_host, self.listen_port)
        await self.site.start()
        self.port = self.site._server.sockets[0].getsockname()[1]
        if self.access_port is None or self.access_port == 0:
            self.access_port = self.port
        self._is_running = True
        self.LOGGER.info(f"ImageServer started on {self.listen_host}:{self.port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
        self._is_running = False
        # Cleanup any remaining files
        for path, delete, future in self.images.values():
            if delete and os.path.exists(path):
                os.remove(path)
            if future and not future.done():
                future.cancel()
        self.images.clear()
        self.LOGGER.info("ImageServer stopped")

    def register_image(self, file_path: str, delete_on_serve: bool = False, future: asyncio.Future = None) -> str:
        """Registers a file to be served and returns its access URL."""
        if not self._is_running:
            raise RuntimeError("ImageServer is not running")
        
        image_id = str(uuid.uuid4())
        self.images[image_id] = (file_path, delete_on_serve, future)
        
        # Schedule cleanup to prevent leaks if the plate never fetches the image
        if delete_on_serve:
            asyncio.create_task(self._cleanup_abandoned(image_id, 30))
            
        access_url = f"http://{self.access_host}:{self.access_port}/{image_id}"
        return access_url

    async def _cleanup_abandoned(self, image_id: str, delay: int):
        await asyncio.sleep(delay)
        if image_id in self.images:
            path, delete, future = self.images.pop(image_id)
            if delete and os.path.exists(path):
                os.remove(path)
            if future and not future.done():
                future.cancel()
            self.LOGGER.debug(f"Cleaned up abandoned image {image_id}")

    async def _serve_file(self, request):
        image_id = request.match_info["image_id"]
        if image_id not in self.images:
            raise web.HTTPNotFound()

        path, delete_on_serve, future = self.images[image_id]
        
        response = web.StreamResponse()
        response.content_type = 'application/octet-stream'
        response.content_length = os.path.getsize(path)
        await response.prepare(request)
        
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                await response.write(chunk)
                
        await response.write_eof()
        
        if future and not future.done():
            future.set_result(True)
            
        if delete_on_serve:
            del self.images[image_id]
            if os.path.exists(path):
                os.remove(path)
                
        return response
