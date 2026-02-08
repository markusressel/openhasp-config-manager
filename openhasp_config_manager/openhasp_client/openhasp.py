import asyncio
from typing import Dict, List, Any, Callable, Tuple, Optional, Awaitable

import orjson

from openhasp_config_manager.openhasp_client.image_processor import OpenHaspImageProcessor
from openhasp_config_manager.openhasp_client.model.configuration.gui_config import GuiConfig
from openhasp_config_manager.openhasp_client.model.configuration.hasp_config import HaspConfig
from openhasp_config_manager.openhasp_client.model.configuration.http_config import HttpConfig
from openhasp_config_manager.openhasp_client.model.configuration.mqtt_config import MqttConfig
from openhasp_config_manager.openhasp_client.model.device import Device
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
        listen_port: int = 0,
        access_port: int = None,
        timeout: int = 10,
        size: Tuple[int or None, int or None] = (None, None),
        fitscreen: bool = False,
    ):
        """
        Sets the image of an object.
        If the image is a URL, it will be fetched first.
        The image will then be converted to RGB565 and
        served by a temporary webserver for the plate to fetch it.

        Note: If you are calling this function concurrently, be aware that under
        the hood a free and unoccupied port is required to feed the image to the
        plate. If you cannot use different ports for each call, make sure to add
        a locking mechanism to avoid multiple threads from creating a webserver
        on the same port.

        :param obj: the object to set the image for
        :param image: the image to set, can be a URL or anything that can be opened by PIL.Image.open, f.ex. a file path
        :param access_host: the address at which the device this webserver is running on is accessible to the plate
        :param access_port: the port to bind the webserver to, defaults to 0 (random free port)
        :param listen_host: the address to bind the webserver to
        :param timeout: the timeout in seconds to wait for the image to be fetched by the plate
        :param size: the size of the image
        :param fitscreen: if True, the image will be resized to fit the screen
        """
        if access_port is None:
            access_port = listen_port

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
                listen_port=listen_port,
                access_host=access_host,
                access_port=access_port,
                timeout=timeout
            )

    async def _serve_image(
        self,
        obj: str,
        image_file,
        listen_host: str,
        access_host: str,
        listen_port: int = 0,
        access_port: int = 0,
        timeout: int = 5,
    ):
        """
        Serves an image using a temporary webserver.

        Note that this webserver intentionally does **not** use HTTPS, since openhasp
        does not support SSL connections. The source file can use an HTTPS source regardless,
        since openhasp-config-manager will fetch the image from the source directly,
        convert it for the plate, and then serve it internally via HTTP.

        :param obj: the object to set the image for
        :param image_file: the image to serve
        :param listen_host: the address to bind the webserver to
        :param listen_port: the port to bind the webserver to, defaults to 0 (random free port)
        :param access_host: the address at which the device this webserver is running on is accessible to the plate
        :param access_port: the port at which the device this webserver is running on is accessible to the plate
        :param timeout: the timeout in seconds after which the webserver will be stopped
        :return: the URL to retrieve the image
        """
        from aiohttp import web

        async def serve_file(request):
            response = web.FileResponse(image_file.path)
            request.app["served"].set_result(True)
            return response

        async def start_server(app, listen_host, listen_port, access_host, access_port, timeout):
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, listen_host, listen_port)
            await site.start()

            port = site._server.sockets[0].getsockname()[1]
            if access_port == 0:
                access_port = port

            listen_url = f"http://{listen_host}:{port}/"
            access_url = f"http://{access_host}:{access_port}/"
            print(f"Serving on {listen_url}, accessible via {access_url}")

            # give the server some time to start
            await asyncio.sleep(1)

            # set the object properties to point to the image url, the plate will download the image immediately
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
            listen_port=listen_port,
            access_host=access_host,
            access_port=access_port,
            timeout=timeout
        )

    async def set_object_properties(self, obj: str, properties: Dict[str, Any]):
        """
        Set the property state of on object
        :param obj: object to set a state for
        :param properties: properties to set
        """
        for prop, value in properties.items():
            keyword = f"{obj}.{prop}"
            # intentionally do not set the keyword parameter,
            # to avoid empty values being interpreted as a
            # "get the current value" request.
            await self.command(
                params=f"{keyword}={value}",
            )

    async def get_object_property(self, obj: str, prop: str, timeout: float = 1.0) -> Optional[Any]:
        """
        Get the value of an object property.
        Note that this function will subscribe to the corresponding MQTT topic and wait for the device to publish the current value.
        :param obj: the object to get the property for
        :param prop: the keyword of the property to get
        :param timeout: the timeout in seconds to wait for the device to respond
        :return: the current value of the property
        """
        command_keyword = f"{obj}.{prop}"
        raw_state = await self.get_state(command=command_keyword, state=obj, timeout=timeout)
        return raw_state[prop] if isinstance(raw_state, dict) and prop in raw_state else raw_state

    async def get_command_state(self, command: str, prop: Optional[str] = None, timeout: float = 1.0) -> Optional[Any]:
        """
        Get the current state of a command.
        Note that this function will subscribe to the corresponding MQTT topic and wait for the device to publish the current value.
        :param command: the command to get the state for
        :param prop: (optional) the specific property to get from the command state, if the command state is a dict
        :param timeout: the timeout in seconds to wait for the device to respond
        :return: the current value of the command
        """
        raw_state = await self.get_state(command=command, timeout=timeout)
        return raw_state[prop] if isinstance(raw_state, dict) and prop in raw_state else raw_state

    async def get_state(self, command: str, state: str = None, timeout: float = 1.0) -> Optional[Any]:
        """
        Get the value of an object property.
        Note that this function will subscribe to the corresponding MQTT topic and wait for the device to publish the current value.
        :param command: the command to get the state for, can be an object property command like "p1b2.text" or a general command like "backlight",
        :param state: the state keyword to get the value for e.g. "p1b2" for "p1b2.text" (because there is no separate "state" topic for each property, but only for the whole object), or "backlight" for "backlight" command (because the state topic is the same as the command keyword)
        :param timeout: the timeout in seconds to wait for the device to respond
        :return: the current value of the property
        """
        if state is None:
            state = command

        command_keyword = command
        listen_path = f"state/{state}"
        future = asyncio.get_event_loop().create_future()

        async def _callback(event_topic: str, event_payload: bytes):
            if not future.done():
                try:
                    # OpenHASP state payloads are usually JSON: {"text": "12345", "val": 10, ...}
                    data = orjson.loads(event_payload)
                    future.set_result(data)
                except Exception:
                    # If it's not JSON, just return the raw payload
                    future.set_result(event_payload.decode('utf-8'))

        await self.listen_event(
            path=listen_path,
            callback=_callback,
        )

        await self.command(
            keyword=command_keyword,
        )

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"Timeout: Device did not respond to {listen_path} within {timeout}s")
            return None

    async def set_idle_state(self, state: str):
        """
        Forces the given idle state
        :param state: one of "off", "short", "long"
        """
        return await self.command(
            keyword="idle",
            params=state
        )

    async def set_backlight(self, state: bool = None, brightness: int = None):
        """
        Sets the backlight state and brightness
        :param state: (optional)True to turn on, False to turn off
        :param brightness: (optional) the brightness level in 0..255
        """
        params = {
            "state": state,
            "brightness": brightness,
        }
        # remove None values
        params = {k: v for k, v in params.items() if v is not None}
        if not params:
            raise ValueError("At least one of 'state' or 'brightness' must be set")

        return await self.command(
            keyword="backlight",
            params=params
        )

    async def get_backlight(self) -> Dict[str, Any]:
        """
        Gets the current backlight state and brightness
        :return: a dict containing the current backlight state and brightness
        """
        return await self.get_command_state(command="backlight")

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
            keyword="page",
            params=f"{index}"
        )

    async def next_page(self):
        """
        Set the next page
        """
        return await self.command(
            keyword="page",
            params="next"
        )

    async def previous_page(self):
        """
        Set the previous page
        """
        return await self.command(
            keyword="page",
            params="prev"
        )

    async def clear_current_page(self):
        """
        Clear the current page
        """
        return await self.command(
            keyword="clearpage",
        )

    async def clear_page(self, page: int):
        """
        Clear the given page
        :param page: the page index to clear
        """
        return await self.command(
            keyword="clearpage",
            params=page
        )

    async def clear_all_pages(self):
        """
        Clear all pages
        """
        return await self.command(
            keyword="clearpage",
            params="all"
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

    async def listen_state(self, obj: str, callback: Callable[[str, bytes], Awaitable[None]]):
        """
        Listen to OpenHASP state events
        :param obj: object to listen to
        :param callback: callback to call when a matching event is received
        """

        async def _callback(event_topic: str, event_payload: bytes):
            await callback(event_topic, event_payload)

        await self.listen_event(
            path=f"state/{obj}",
            callback=_callback,
        )

    async def listen_event(self, path: str, callback: Callable[[str, bytes], Awaitable[None]]):
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

    async def command(self, keyword: str = None, params: Any = None):
        """
        Execute a command on a device
        See: https://www.openhasp.com/0.7.0/commands/mqtt/#issuing-commands

        :param keyword: (optional) keyword of the command
        :param params: parameters for the command
        """
        topic = f"hasp/{self._device.config.mqtt.name}/command"
        if keyword is not None:
            topic += f"/{keyword}"
        await self._mqtt_client.publish(topic=topic, payload=params)

    async def jsonl(self, jsonl: str | dict):
        """
        Send a JSONL string to the device.
        See: https://www.openhasp.com/0.7.0/commands/?h=jsonl#jsonl
        :param jsonl: the JSONL string (or object) to send
        """
        await self.command(keyword="jsonl", params=jsonl)

    async def clear_object(self, obj: str):
        """
        Delete the children from the object on the device.
        See: https://www.openhasp.com/0.7.0/design/objects/#common-methods
        :param obj: the object to clear, f.ex. "p1b2"
        """
        await self.command(keyword=f"{obj}.clear", )

    async def clear_object_id(self, page: int, obj: int):
        """
        Delete the children from the object on a specific page.
        See: https://www.openhasp.com/0.7.0/design/objects/#common-methods
        :param page: the page index
        :param obj: the object index
        """
        object_id = self.compute_object_id(page, obj)
        await self.clear_object(object_id)

    async def delete_object(self, obj: str):
        """
        Delete the object and its children from the page.
        See: https://www.openhasp.com/0.7.0/design/objects/#common-methods
        :param obj: the object to delete, f.ex. "p1b2"
        """
        await self.command(keyword=f"{obj}.delete", )

    async def delete_object_id(self, page: int, obj: int):
        """
        Delete the object and its children from the page.
        See: https://www.openhasp.com/0.7.0/design/objects/#common-methods
        :param page: the page index
        :param obj: the object index
        """
        object_id = self.compute_object_id(page, obj)
        await self.delete_object(object_id)

    async def bring_object_to_front(self, obj: str):
        """
        Bring an object to the front of the page.
        See: https://www.openhasp.com/0.7.0/design/objects/#common-methods
        :param obj: the object to bring to the front, f.ex. "p1b2"
        """
        await self.command(keyword=f"{obj}.to_front", )

    async def bring_object_to_front_id(self, page: int, obj: int):
        """
        Bring an object to the front of a specific page.
        See: https://www.openhasp.com/0.7.0/design/objects/#common-methods
        :param page: the page index
        :param obj: the object index
        """
        object_id = self.compute_object_id(page, obj)
        await self.bring_object_to_front(object_id)

    async def bring_object_to_back(self, obj: str):
        """
        Bring an object to the back of the page.
        See: https://www.openhasp.com/0.7.0/design/objects/#common-methods
        :param obj: the object to bring to the back, f.ex. "p1b2"
        """
        await self.command(keyword=f"{obj}.to_back", )

    async def bring_object_to_back_id(self, page: int, obj: int):
        """
        Bring an object to the back of a specific page.
        See: https://www.openhasp.com/0.7.0/design/objects/#common-methods
        :param page: the page index
        :param obj: the object index
        """
        object_id = self.compute_object_id(page, obj)
        await self.bring_object_to_back(object_id)

    def get_files(self) -> List[str]:
        """
        Retrieve a list of all file on the device
        :return: a list of all files on the device
        """
        return self._webservice_client.get_files()

    def get_file_content(self, file_name: str) -> Optional[bytes]:
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

    def get_http_config(self) -> HttpConfig:
        """
        Get the HTTP configuration
        :return: the HTTP configuration
        """
        return self._webservice_client.get_http_config()

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

    def get_gui_config(self) -> GuiConfig:
        """
        Get the GUI configuration
        :return: the GUI configuration
        """
        return self._webservice_client.get_gui_config()

    def set_gui_config(self, config: GuiConfig):
        """
        Set the GUI configuration
        :param config: the configuration to set
        :return:
        """
        self._webservice_client.set_gui_config(config)

    def upload_files(self, files: Dict[str, bytes]):
        """
        Upload a collection of files
        :param files: "target file name"->"file content" mapping
        """
        self._webservice_client.upload_files(files)

    def upload_file(self, name: str, content: bytes):
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

    @staticmethod
    def compute_object_id(page: int, obj: int) -> str:
        """
        Creates an object ID for a given page and object index.
        :param page: the page index
        :param obj: the object index
        :return: the object ID in the format "p{page}b{obj}"
        """
        return f"p{page}b{obj}" if page >= 0 else obj
