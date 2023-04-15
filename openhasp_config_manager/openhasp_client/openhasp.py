import asyncio
from typing import Dict, List, Any, Callable, Tuple

from asyncio_mqtt import Topic

from openhasp_config_manager.openhasp_client.image_processor import OpenHaspImageProcessor
from openhasp_config_manager.openhasp_client.model.device import Device
from openhasp_config_manager.openhasp_client.model.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.http_config import HttpConfig
from openhasp_config_manager.openhasp_client.model.mqtt_config import MqttConfig
from openhasp_config_manager.openhasp_client.mqtt_client import MqttClient
from openhasp_config_manager.openhasp_client.telnet_client import OpenHaspTelnetClient
from openhasp_config_manager.openhasp_client.webservice_client import WebserviceClient
from openhasp_config_manager.ui.util import info


class OpenHaspClient:

    def __init__(self, device: Device):
        """
        :param device: the device this client can communicate with
        """
        self._device = device

        self._image_processor = OpenHaspImageProcessor()

        self._webservice_client = WebserviceClient(
            url=device.config.openhasp_config_manager.device.ip,
            username=self._device.config.http.user,
            password=self._device.config.http.password
        )

        self._mqtt_client = MqttClient(
            host=device.config.mqtt.host,
            port=device.config.mqtt.port,
            mqtt_user=device.config.mqtt.user,
            mqtt_password=device.config.mqtt.password
        )

        self._telnet_client = OpenHaspTelnetClient(
            host=device.config.openhasp_config_manager.device.ip,
            port=device.config.telnet.port,
            baudrate=device.config.debug.baud,
            user=device.config.http.user,
            password=device.config.http.password,
        )

    async def send_image(self, image: any, page: int, object_id: int):
        """
        Send an image to the device
        :param image: the image to send
        :param page: the page to send the image to
        :param object_id: the object id to send the image to
        """
        pass

    async def set_text(self, obj: str, text: str):
        """
        Set the text of an object
        :param obj: the object to set the text for
        :param text: the text to set
        """
        await self.set_object_properties(obj, {"text": text})

    async def set_image(
        self,
        obj: str,
        image,
        access_host: str,
        listen_host: str = "0.0.0.0",
        timeout: int = 10,
        size: Tuple[int or None, int or None] = (None, None),
        fitscreen: bool = False,
    ):
        """
        Sets the image of an object.
        If the image is a URL, it will be fetched first.
        The image will then be converted to RGB565 and
        served by a temporary webserver for the plate to fetch it.

        :param obj: the object to set the image for
        :param image: the image to set
        :param access_host: the address at which the device this webserver is running on is accessible to the plate
        :param listen_host: the address to bind the webserver to
        :param timeout: the timeout in seconds to wait for the image to be fetched by the plate
        :param size: the size of the image
        :param fitscreen: if True, the image will be resized to fit the screen
        """
        import temppathlib
        with temppathlib.NamedTemporaryFile() as out_image:
            self._image_processor.image_to_rgb565(
                in_image=image,
                out_image=out_image.file,
                size=size,
                fitscreen=fitscreen
            )
            await self._serve_image(
                obj=obj,
                image_file=out_image,
                listen_host=listen_host,
                access_host=access_host,
                timeout=timeout
            )

    async def _serve_image(self, obj: str, image_file, listen_host: str, access_host: str, timeout: int):
        """
        Serves an image using a temporary webserver
        :param image_file: the image to serve
        :param listen_host: the address to bind the webserver to
        :param access_host: the address at which the device this webserver is running on is accessible to the plate
        :param timeout: the timeout in seconds after which the webserver will be stopped
        :return: the URL to retrieve the image
        """
        from aiohttp import web

        async def serve_file(request):
            response = web.FileResponse(image_file.path)
            request.app["served"].set_result(True)
            return response

        async def start_server(app, listen_host, access_host, port, timeout):
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, listen_host, port)
            await site.start()

            port = site._server.sockets[0].getsockname()[1]

            listen_url = f"http://{listen_host}:{port}/"
            access_url = f"http://{access_host}:{port}/"
            print(f"Serving on {listen_url}, accessible via {access_url}")

            await asyncio.sleep(1)

            await self.set_object_properties(
                obj=obj,
                properties={
                    "src": access_url
                }
            )

            try:
                await asyncio.wait_for(app["served"], timeout)
            except asyncio.TimeoutError:
                print(f"Timeout reached after {timeout} seconds. Server stopped.")
            finally:
                await runner.cleanup()

            return listen_url

        app = web.Application()
        app["served"] = asyncio.Future()

        app.router.add_route("GET", "/", serve_file)

        await start_server(
            app=app,
            listen_host=listen_host,
            access_host=access_host,
            port=0,  # let the system pick a random free port for us
            timeout=timeout
        )

    async def set_object_properties(self, obj: str, properties: Dict[str, Any]):
        """
        Set the state of a plate
        :param obj: object to set a state for
        :param properties: properties to set
        """
        for prop, value in properties.items():
            await self.command(
                name=f"{obj}.{prop}",
                params=value,
            )

    async def set_idle_state(self, state: str):
        """
        Forces the given idle state
        :param state: one of "off", "short", "long"
        """
        return await self.command(
            name="idle",
            params=state
        )

    async def set_backlight(self, state: bool, brightness: int):
        """
        Sets the backlight state and brightness
        :param state: True to turn on, False to turn off
        :param brightness: the brightness level in 0..255
        """
        return await self.command(
            name="backlight",
            params={
                "state": state,
                "brightness": brightness,
            }
        )

    async def wakeup(self):
        """
        Wakes up the display
        """
        return await self.set_idle_state(state="off")

    async def set_page(self, index: int):
        """
        Set the current page
        :param index: the index of the page to set
        """
        return await self.command(
            name="page",
            params=f"{index}"
        )

    async def set_hidden(self, obj: str, hidden: bool):
        """
        Set the "hidden" property of an object
        :param obj: the object to set the property for
        :param hidden: True to hide the object, False to show it
        """
        return await self.set_object_properties(
            obj=obj,
            properties={
                "hidden": "1" if hidden else "0",
            }
        )

    async def listen_state(self, obj: str, callback: Callable):
        """
        Listen to OpenHASP state events
        :param obj: object to listen to
        :param callback: callback to call when a matching event is received
        """

        async def _callback(event_topic: Topic, event_payload: bytes):
            await callback(str(event_topic), event_payload)

        await self.listen_event(
            path=f"state/{obj}",
            callback=_callback,
        )

    async def listen_event(self, path: str, callback: Callable):
        """
        Listen to OpenHASP events related to this device
        :param path: MQTT subpath to listen to
        :param callback: callback to call when a matching event is received
        """
        topic = f"hasp/{self._device.config.mqtt.name}/{path}"
        await self._mqtt_client.subscribe(topic, callback)

    async def cancel_callback(self, callback: Callable = None):
        """
        Cancel a callback which was previously registered, f.ex. via listen_event (or listen_state)
        :param callback: the specific callback to cancel
        """
        await self._mqtt_client.cancel_callback(callback=callback)

    async def command(self, name: str, params: any):
        """
        Execute a command on a device
        :param name: the name of the command
        :param params: parameters for the command
        """
        topic = f"hasp/{self._device.config.mqtt.name}/command/{name}"
        await self._mqtt_client.publish(topic=topic, payload=params)

    def get_files(self) -> List[str]:
        """
        Retrieve a list of all file on the device
        :return: a list of all files on the device
        """
        return self._webservice_client.get_files()

    def get_file_content(self, file_name: str) -> str or None:
        return self._webservice_client.get_file_content(file_name)

    def delete_file(self, file_name: str):
        """
        Delete a file on the device
        :param file_name: the name of the file
        """
        self._webservice_client.delete_file(file_name)

    def reboot(self):
        """
        Request a reboot
        """
        self._webservice_client.reboot()

    def set_hasp_config(self, config: HaspConfig):
        """
        Set the "HASP" configuration
        :param config: the configuration to set
        """
        self._webservice_client.set_hasp_config(config)

    def set_http_config(self, config: HttpConfig):
        """
        Set the HTTP configuration
        :param config: the configuration to set
        """
        self._webservice_client.set_http_config(config)

    def get_mqtt_config(self) -> MqttConfig:
        return self._webservice_client.get_mqtt_config()

    def set_mqtt_config(self, config: MqttConfig):
        """
        Set the MQTT configuration
        :param config: the configuration to set
        :return:
        """
        self._webservice_client.set_mqtt_config(config)

    def set_gui_config(self, config: GuiConfig):
        """
        Set the GUI configuration
        :param config: the configuration to set
        :return:
        """
        self._webservice_client.set_gui_config(config)

    def upload_files(self, files: Dict[str, str]):
        """
        Upload a collection of files
        :param files: "target file name"->"file content" mapping
        """
        self._webservice_client.upload_files(files)

    def upload_file(self, name: str, content: str):
        """
        Upload a single file
        :param name: the target name of the file on the device
        :param content: the file content
        """
        info(f"Uploading '{name}'...")
        self._webservice_client.upload_file(name, content)

    def take_screenshot(self) -> bytes:
        """
        Requests a screenshot from the device.
        :return:
        """
        return self._webservice_client.take_screenshot()

    async def shell(self):
        await self._telnet_client.shell()

    async def logs(self):
        await self._telnet_client.logs()
