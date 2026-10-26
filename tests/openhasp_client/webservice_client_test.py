import aiohttp
import pytest

from openhasp_config_manager.openhasp_client.webservice_client import WebserviceClient


def test_requests_without_files_have_the_normal_timeout():
    assert WebserviceClient._timeout_seconds(None) == 5


def test_big_uploads_get_more_time():
    assert WebserviceClient._timeout_seconds({"a.ttf": bytes(464_000)}) > 25
    assert WebserviceClient._timeout_seconds({"a.cmd": b"run L:/x"}) < 6


async def _upload_with_reply(monkeypatch, error):
    client = WebserviceClient(url="plate", username="u", password="p")

    async def fail(**kwargs):
        raise error

    monkeypatch.setattr(client, "_do_request", fail)
    await client.upload_file("a.bin", b"data")


async def test_upload_with_the_malformed_reply_of_the_plate_is_stored(monkeypatch):
    error = aiohttp.ClientResponseError(
        request_info=None, history=(), status=400, message="Data after `Connection: close`:\n\n  b'Upload OKHTTP/1.1 200 OK'"
    )

    await _upload_with_reply(monkeypatch, error)


async def test_other_upload_errors_are_raised(monkeypatch):
    error = aiohttp.ClientResponseError(request_info=None, history=(), status=500, message="no space left")

    with pytest.raises(aiohttp.ClientResponseError):
        await _upload_with_reply(monkeypatch, error)
