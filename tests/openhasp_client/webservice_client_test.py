from openhasp_config_manager.openhasp_client.webservice_client import WebserviceClient


def test_requests_without_files_have_the_normal_timeout():
    assert WebserviceClient._timeout_seconds(None) == 5


def test_big_uploads_get_more_time():
    assert WebserviceClient._timeout_seconds({"a.ttf": bytes(464_000)}) > 25
    assert WebserviceClient._timeout_seconds({"a.cmd": b"run L:/x"}) < 6
