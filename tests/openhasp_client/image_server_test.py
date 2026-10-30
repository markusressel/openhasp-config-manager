import asyncio
import logging
import socket
import struct

import pytest

from openhasp_config_manager.openhasp_client.image_server import ImageServer


@pytest.mark.asyncio
async def test_a_plate_that_stops_fetching_is_a_warning_and_the_image_stays(tmp_path, caplog):
    # GIVEN: an image too large to be sent at once
    server = ImageServer(listen_host="127.0.0.1", listen_port=0, access_host="127.0.0.1")
    await server.start()
    file = tmp_path / "image.bin"
    file.write_bytes(b"x" * 20_000_000)
    url = server.register_image(str(file), delete_on_serve=True)
    image_id = url.rsplit("/", 1)[1]

    try:
        # WHEN: the plate resets the connection after the first bytes
        with caplog.at_level(logging.WARNING):
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            writer.write(f"GET /{image_id} HTTP/1.1\r\nHost: plate\r\n\r\n".encode())
            await writer.drain()
            await reader.read(1024)
            sock = writer.get_extra_info("socket")
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            writer.close()
            for _ in range(200):
                if any("stopped fetching" in record.message for record in caplog.records):
                    break
                await asyncio.sleep(0.01)

        # THEN
        assert any(
            record.levelno == logging.WARNING and f"stopped fetching image {image_id}" in record.message
            for record in caplog.records
        )
        assert not any(record.name == "aiohttp.server" for record in caplog.records)
        assert image_id in server.images and file.exists()
    finally:
        await server.stop()
