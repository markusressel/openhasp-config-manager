import asyncio
from enum import Enum
from typing import Dict, List, Any, Callable, Tuple

from aiomqtt import Topic

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


class IntegratedIcon(Enum):
    """
    Definition of the integrated icons used in OpenHASP.
    """
    ARROW_DOWN = ("\uE045", "arrow-down")
    BATTERY_HIGH = ("\uF2A3", "battery-high")
    ARROW_DOWN_BOX = ("\uE6C0", "arrow-down-box")
    BATTERY_LOW = ("\uF2A1", "battery-low")
    ARROW_LEFT = ("\uE04D", "arrow-left")
    BATTERY_MEDIUM = ("\uF2A2", "battery-medium")
    ARROW_RIGHT = ("\uE054", "arrow-right")
    BATTERY_OUTLINE = ("\uE08E", "battery-outline")
    ARROW_UP = ("\uE05D", "arrow-up")
    EV_STATION = ("\uE5F1", "ev-station")
    ARROW_UP_BOX = ("\uE6C3", "arrow-up-box")
    LEAF = ("\uE32A", "leaf")
    CHEVRON_DOWN = ("\uE140", "chevron-down")
    LIGHTNING_BOLT = ("\uF40B", "lightning-bolt")
    CHEVRON_LEFT = ("\uE141", "chevron-left")
    POWER = ("\uE425", "power")
    CHEVRON_RIGHT = ("\uE142", "chevron-right")
    POWER_PLUG = ("\uE6A5", "power-plug")
    CHEVRON_UP = ("\uE143", "chevron-up")
    CEILING_LIGHT = ("\uE769", "ceiling-light")
    SUBDIRECTORY_ARROW_LEFT = ("\uE60C", "subdirectory-arrow-left")
    COACH_LAMP = ("\uF020", "coach-lamp")
    AIR_CONDITIONER = ("\uE01B", "air-conditioner")
    DESK_LAMP = ("\uE95F", "desk-lamp")
    CLOUD_SEARCH_OUTLINE = ("\uE957", "cloud-search-outline")
    FLOOR_LAMP = ("\uE8DD", "floor-lamp")
    FIRE = ("\uE238", "fire")
    LAMP = ("\uE6B5", "lamp")
    RADIATOR = ("\uE438", "radiator")
    LIGHTBULB = ("\uE335", "lightbulb")
    RADIATOR_DISABLED = ("\uEAD7", "radiator-disabled")
    LIGHTBULB_ON = ("\uE6E8", "lightbulb-on")
    SNOWFLAKE = ("\uE717", "snowflake")
    OUTDOOR_LAMP = ("\uF054", "outdoor-lamp")
    THERMOMETER = ("\uE50F", "thermometer")
    STRING_LIGHTS = ("\uF2BA", "string-lights")
    WATER = ("\uE58C", "water")
    VANITY_LIGHT = ("\uF1E1", "vanity-light")
    WATER_PERCENT = ("\uE58E", "water-percent")
    WALL_SCONCE = ("\uE91C", "wall-sconce")
    WEATHER_CLOUDY = ("\uE590", "weather-cloudy")
    CHECK = ("\uE12C", "check")
    WEATHER_FOG = ("\uE591", "weather-fog")
    CLOSE = ("\uE156", "close")
    WEATHER_HAIL = ("\uE592", "weather-hail")
    COG = ("\uE493", "cog")
    WEATHER_LIGHTNING = ("\uE593", "weather-lightning")
    DOTS_VERTICAL = ("\uE1D9", "dots-vertical")
    WEATHER_LIGHTNING_RAINY = ("\uE67E", "weather-lightning-rainy")
    HOME = ("\uE2DC", "home")
    WEATHER_NIGHT = ("\uE594", "weather-night")
    HOME_OUTLINE = ("\uE6A1", "home-outline")
    WEATHER_PARTLY_CLOUDY = ("\uE595", "weather-partly-cloudy")
    MINUS = ("\uE374", "minus")
    WEATHER_POURING = ("\uE596", "weather-pouring")
    PLUS = ("\uE415", "plus")
    WEATHER_RAINY = ("\uE597", "weather-rainy")
    BED = ("\uE2E3", "bed")
    WEATHER_SNOWY = ("\uE598", "weather-snowy")
    CAR = ("\uE10B", "car")
    WEATHER_SNOWY_RAINY = ("\uE67F", "weather-snowy-rainy")
    COFFEE = ("\uE176", "coffee")
    WEATHER_SUNNY = ("\uE599", "weather-sunny")
    POOL = ("\uE606", "pool")
    WEATHER_WINDY = ("\uE59D", "weather-windy")
    SHOWER = ("\uE9A0", "shower")
    WEATHER_WINDY_VARIANT = ("\uE59E", "weather-windy-variant")
    SILVERWARE_FORK_KNIFE = ("\uEA70", "silverware-fork-knife")
    WHITE_BALANCE_SUNNY = ("\uE5A8", "white-balance-sunny")
    SOFA = ("\uE4B9", "sofa")
    CALENDAR = ("\uE0ED", "calendar")
    TOILET = ("\uE9AB", "toilet")
    CLOCK_OUTLINE = ("\uE150", "clock-outline")
    ACCOUNT = ("\uE004", "account")
    HISTORY = ("\uE2DA", "history")
    HUMAN_GREETING = ("\uE64A", "human-greeting")
    TIMER_OUTLINE = ("\uE51B", "timer-outline")
    RUN = ("\uE70E", "run")
    BLUETOOTH = ("\uE0AF", "bluetooth")
    ALERT = ("\uE026", "alert")
    WIFI = ("\uE5A9", "wifi")
    CCTV = ("\uE7AE", "cctv")
    BLINDS = ("\uE0AC", "blinds")
    DOOR_CLOSED = ("\uE81B", "door-closed")
    BLINDS_OPEN = ("\uF011", "blinds-open")
    DOOR_CLOSED_LOCK = ("\uF0AF", "door-closed-lock")
    GARAGE_OPEN_VARIANT = ("\uF2D4", "garage-open-variant")
    DOOR_OPEN = ("\uE81C", "door-open")
    GARAGE_VARIANT = ("\uF2D3", "garage-variant")
    KEY_VARIANT = ("\uE30B", "key-variant")
    WINDOW_SHUTTER = ("\uF11C", "window-shutter")
    LOCK = ("\uE33E", "lock")
    WINDOW_SHUTTER_ALERT = ("\uF11D", "window-shutter-alert")
    LOCK_OPEN_VARIANT = ("\uEFC6", "lock-open-variant")
    WINDOW_SHUTTER_OPEN = ("\uF11E", "window-shutter-open")
    SHIELD_CHECK = ("\uE565", "shield-check")
    BELL = ("\uE09A", "bell")
    SHIELD_HOME = ("\uE68A", "shield-home")
    CELLPHONE = ("\uE11C", "cellphone")
    SHIELD_LOCK = ("\uE99D", "shield-lock")
    DISHWASHER = ("\uEAAC", "dishwasher")
    WINDOW_CLOSED_VARIANT = ("\uF1DB", "window-closed-variant")
    ENGINE = ("\uE1FA", "engine")
    MONITOR_SPEAKER = ("\uEF5F", "monitor-speaker")
    FAN = ("\uE210", "fan")
    MUSIC = ("\uE75A", "music")
    FOUNTAIN = ("\uE96B", "fountain")
    PAUSE = ("\uE3E4", "pause")
    FRIDGE_OUTLINE = ("\uE28F", "fridge-outline")
    PLAY = ("\uE40A", "play")
    KETTLE = ("\uE5FA", "kettle")
    REPEAT = ("\uE456", "repeat")
    LAPTOP = ("\uE322", "laptop")
    REPEAT_OFF = ("\uE457", "repeat-off")
    MICROWAVE = ("\uEC99", "microwave")
    REPEAT_ONCE = ("\uE458", "repeat-once")
    RECYCLE_VARIANT = ("\uF39D", "recycle-variant")
    SHUFFLE = ("\uE49D", "shuffle")
    ROBOT_MOWER_OUTLINE = ("\uF1F3", "robot-mower-outline")
    SHUFFLE_DISABLED = ("\uE49E", "shuffle-disabled")
    ROBOT_VACUUM = ("\uE70D", "robot-vacuum")
    SKIP_NEXT = ("\uE4AD", "skip-next")
    STOVE = ("\uE4DE", "stove")
    SKIP_PREVIOUS = ("\uE4AE", "skip-previous")
    TELEVISION = ("\uE502", "television")
    SPEAKER = ("\uE4C3", "speaker")
    TRASH_CAN_OUTLINE = ("\uEA7A", "trash-can-outline")
    STOP = ("\uE4DB", "stop")
    TUMBLE_DRYER = ("\uE917", "tumble-dryer")
    VOLUME_HIGH = ("\uE57E", "volume-high")
    WASHING_MACHINE = ("\uE72A", "washing-machine")
    VOLUME_MEDIUM = ("\uE580", "volume-medium")
    WATER_PUMP = ("\uE58F", "water-pump")
    VOLUME_MUTE = ("\uE75F", "volume-mute")
    ARROW_LEFT_BOX = ("\uE6C1", "arrow-left-box")
    SOLAR_PANEL = ("\uED9B", "solar-panel")
    ARROW_RIGHT_BOX = ("\uE6C2", "arrow-right-box")
    SOLAR_PANEL_LARGE = ("\uED9C", "solar-panel-large")
    RADIATOR_OFF = ("\uEAD8", "radiator-off")
    SOLAR_POWER = ("\uEA72", "solar-power")
    WEATHER_HAZY = ("\uEF30", "weather-hazy")
    SOLAR_POWER_VARIANT_OUTLINE = ("\uFA74", "solar-power-variant-outline")
    WEATHER_NIGHT_PARTLY_CLOUDY = ("\uEF31", "weather-night-partly-cloudy")
    TRANSMISSION_TOWER_IMPORT = ("\uF92D", "transmission-tower-import")
    TRANSMISSION_TOWER = ("\uED3E", "transmission-tower")
    TRANSMISSION_TOWER_EXPORT = ("\uF92C", "transmission-tower-export")

    @classmethod
    def entries(cls) -> List[Tuple[str, str]]:
        """
        Returns a list of tuples containing the unicode value and the name of icon in mdi.
        """
        return [(member.value[0], member.value[1]) for member in cls]


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
        access_port: int = 0,
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
        :param access_port: the port to bind the webserver to, defaults to 0 (random free port)
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
                access_port=access_port,
                timeout=timeout
            )

    async def _serve_image(
        self,
        obj: str,
        image_file,
        listen_host: str,
        access_host: str,
        access_port: int = 0,
        timeout: int = 5,
    ):
        """
        Serves an image using a temporary webserver
        :param obj: the object to set the image for
        :param image_file: the image to serve
        :param listen_host: the address to bind the webserver to
        :param access_host: the address at which the device this webserver is running on is accessible to the plate
        :param access_port: the port to bind the webserver to, defaults to 0 (random free port)
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
            port=access_port,
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

    async def next_page(self):
        """
        Set the next page
        """
        return await self.command(
            name="page",
            params="next"
        )

    async def previous_page(self):
        """
        Set the previous page
        """
        return await self.command(
            name="page",
            params="prev"
        )

    async def clear_current_page(self):
        """
        Clear the current page
        """
        return await self.command(
            name="clearpage",
        )

    async def clear_page(self, page: int):
        """
        Clear the given page
        :param page: the page index to clear
        """
        return await self.command(
            name="clearpage",
            params=page
        )

    async def clear_all_pages(self):
        """
        Clear all pages
        """
        return await self.command(
            name="clearpage",
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

    def get_file_content(self, file_name: str) -> bytes or None:
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
