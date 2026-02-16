from enum import Enum
from typing import List, Tuple


class IntegratedIcon(Enum):
    """
    Definition of the integrated icons used in OpenHASP.
    OpenHASP 0.7.0 Built-in Material Design Icons.
    Maps icon names to their hex-encoded UTF-16 strings.
    See: https://www.openhasp.com/latest0.7.0/design/fonts/#icons
    """

    # Navigation & Arrows
    ARROW_DOWN = ("\ue045", "arrow-down")
    ARROW_DOWN_BOX = ("\ue6c0", "arrow-down-box")
    ARROW_LEFT = ("\ue04d", "arrow-left")
    ARROW_LEFT_BOX = ("\ue6c1", "arrow-left-box")
    ARROW_RIGHT = ("\ue054", "arrow-right")
    ARROW_RIGHT_BOX = ("\ue6c2", "arrow-right-box")
    ARROW_UP = ("\ue05d", "arrow-up")
    ARROW_UP_BOX = ("\ue6c3", "arrow-up-box")
    CHEVRON_DOWN = ("\ue140", "chevron-down")
    CHEVRON_LEFT = ("\ue141", "chevron-left")
    CHEVRON_RIGHT = ("\ue142", "chevron-right")
    CHEVRON_UP = ("\ue143", "chevron-up")
    SUBDIRECTORY_ARROW_LEFT = ("\ue60c", "subdirectory-arrow-left")

    # Energy & Battery
    BATTERY_HIGH = ("\uf2a3", "battery-high")
    BATTERY_LOW = ("\uf2a1", "battery-low")
    BATTERY_MEDIUM = ("\uf2a2", "battery-medium")
    BATTERY_OUTLINE = ("\ue08e", "battery-outline")
    EV_STATION = ("\ue5f1", "ev-station")
    LIGHTNING_BOLT = ("\uf40b", "lightning-bolt")
    POWER = ("\ue425", "power")
    POWER_PLUG = ("\ue6a5", "power-plug")
    SOLAR_PANEL = ("\ued9b", "solar-panel")
    SOLAR_PANEL_LARGE = ("\ued9c", "solar-panel-large")
    SOLAR_POWER = ("\uea72", "solar-power")
    SOLAR_POWER_VARIANT_OUTLINE = ("\ufa74", "solar-power-variant-outline")
    TRANSMISSION_TOWER = ("\ued3e", "transmission-tower")
    TRANSMISSION_TOWER_EXPORT = ("\uf92c", "transmission-tower-export")
    TRANSMISSION_TOWER_IMPORT = ("\uf92d", "transmission-tower-import")

    # Climate & Weather
    AIR_CONDITIONER = ("\ue01b", "air-conditioner")
    CLOUD_SEARCH_OUTLINE = ("\ue957", "cloud-search-outline")
    FIRE = ("\ue238", "fire")
    RADIATOR = ("\ue438", "radiator")
    RADIATOR_DISABLED = ("\uead7", "radiator-disabled")
    RADIATOR_OFF = ("\uead8", "radiator-off")
    SNOWFLAKE = ("\ue717", "snowflake")
    THERMOMETER = ("\ue50f", "thermometer")
    WATER = ("\ue58c", "water")
    WATER_PERCENT = ("\ue58e", "water-percent")
    WEATHER_CLOUDY = ("\ue590", "weather-cloudy")
    WEATHER_FOG = ("\ue591", "weather-fog")
    WEATHER_HAIL = ("\ue592", "weather-hail")
    WEATHER_HAZY = ("\uef30", "weather-hazy")
    WEATHER_LIGHTNING = ("\ue593", "weather-lightning")
    WEATHER_LIGHTNING_RAINY = ("\ue67e", "weather-lightning-rainy")
    WEATHER_NIGHT = ("\ue594", "weather-night")
    WEATHER_NIGHT_PARTLY_CLOUDY = ("\uef31", "weather-night-partly-cloudy")
    WEATHER_PARTLY_CLOUDY = ("\ue595", "weather-partly-cloudy")
    WEATHER_POURING = ("\ue596", "weather-pouring")
    WEATHER_RAINY = ("\ue597", "weather-rainy")
    WEATHER_SNOWY = ("\ue598", "weather-snowy")
    WEATHER_SNOWY_RAINY = ("\ue67f", "weather-snowy-rainy")
    WEATHER_SUNNY = ("\ue599", "weather-sunny")
    WEATHER_WINDY = ("\ue59d", "weather-windy")
    WEATHER_WINDY_VARIANT = ("\ue59e", "weather-windy-variant")
    WHITE_BALANCE_SUNNY = ("\ue5a8", "white-balance-sunny")

    # Lighting
    CEILING_LIGHT = ("\ue769", "ceiling-light")
    COACH_LAMP = ("\uf020", "coach-lamp")
    DESK_LAMP = ("\ue95f", "desk-lamp")
    FLOOR_LAMP = ("\ue8dd", "floor-lamp")
    LAMP = ("\ue6b5", "lamp")
    LIGHTBULB = ("\ue335", "lightbulb")
    LIGHTBULB_ON = ("\ue6e8", "lightbulb-on")
    OUTDOOR_LAMP = ("\uf054", "outdoor-lamp")
    STRING_LIGHTS = ("\uf2ba", "string-lights")
    VANITY_LIGHT = ("\uf1e1", "vanity-light")
    WALL_SCONCE = ("\ue91c", "wall-sconce")

    # Controls & UI
    CHECK = ("\ue12c", "check")
    CLOSE = ("\ue156", "close")
    COG = ("\ue493", "cog")
    DOTS_VERTICAL = ("\ue1d9", "dots-vertical")
    MINUS = ("\ue374", "minus")
    PLUS = ("\ue415", "plus")
    PAUSE = ("\ue3e4", "pause")
    PLAY = ("\ue40a", "play")
    REPEAT = ("\ue456", "repeat")
    REPEAT_OFF = ("\ue457", "repeat-off")
    REPEAT_ONCE = ("\ue458", "repeat-once")
    SHUFFLE = ("\ue49d", "shuffle")
    SHUFFLE_DISABLED = ("\ue49e", "shuffle-disabled")
    SKIP_NEXT = ("\ue4ad", "skip-next")
    SKIP_PREVIOUS = ("\ue4ae", "skip-previous")
    STOP = ("\ue4db", "stop")
    VOLUME_HIGH = ("\ue57e", "volume-high")
    VOLUME_MEDIUM = ("\ue580", "volume-medium")
    VOLUME_MUTE = ("\ue75f", "volume-mute")

    # Home & Security
    HOME = ("\ue2dc", "home")
    HOME_OUTLINE = ("\ue6a1", "home-outline")
    CCTV = ("\ue7ae", "cctv")
    DOOR_CLOSED = ("\ue81b", "door-closed")
    DOOR_CLOSED_LOCK = ("\uf0af", "door-closed-lock")
    DOOR_OPEN = ("\ue81c", "door-open")
    GARAGE_OPEN_VARIANT = ("\uf2d4", "garage-open-variant")
    GARAGE_VARIANT = ("\uf2d3", "garage-variant")
    KEY_VARIANT = ("\ue30b", "key-variant")
    LOCK = ("\ue33e", "lock")
    LOCK_OPEN_VARIANT = ("\uefc6", "lock-open-variant")
    SHIELD_CHECK = ("\ue565", "shield-check")
    SHIELD_HOME = ("\ue68a", "shield-home")
    SHIELD_LOCK = ("\ue99d", "shield-lock")
    BELL = ("\ue09a", "bell")

    # Household Objects & Devices
    BED = ("\ue2e3", "bed")
    CAR = ("\ue10b", "car")
    COFFEE = ("\ue176", "coffee")
    DISHWASHER = ("\ueaac", "dishwasher")
    ENGINE = ("\ue1fa", "engine")
    FAN = ("\ue210", "fan")
    FOUNTAIN = ("\ue96b", "fountain")
    FRIDGE_OUTLINE = ("\ue28f", "fridge-outline")
    KETTLE = ("\ue5fa", "kettle")
    LAPTOP = ("\ue322", "laptop")
    MICROWAVE = ("\uec99", "microwave")
    RECYCLE_VARIANT = ("\uf39d", "recycle-variant")
    ROBOT_MOWER_OUTLINE = ("\uf1f3", "robot-mower-outline")
    ROBOT_VACUUM = ("\ue70d", "robot-vacuum")
    STOVE = ("\ue4de", "stove")
    TELEVISION = ("\ue502", "television")
    TRASH_CAN_OUTLINE = ("\uea7a", "trash-can-outline")
    TUMBLE_DRYER = ("\ue917", "tumble-dryer")
    WASHING_MACHINE = ("\ue72a", "washing-machine")
    WATER_PUMP = ("\ue58f", "water-pump")
    MONITOR_SPEAKER = ("\uef5f", "monitor-speaker")
    SPEAKER = ("\ue4c3", "speaker")
    CELLPHONE = ("\ue11c", "cellphone")
    MUSIC = ("\ue75a", "music")

    # Windows & Blinds
    BLINDS = ("\ue0ac", "blinds")
    BLINDS_OPEN = ("\uf011", "blinds-open")
    WINDOW_SHUTTER = ("\uf11c", "window-shutter")
    WINDOW_SHUTTER_ALERT = ("\uf11d", "window-shutter-alert")
    WINDOW_SHUTTER_OPEN = ("\uf11e", "window-shutter-open")
    WINDOW_CLOSED_VARIANT = ("\uf1db", "window-closed-variant")

    # Presence & Misc
    ACCOUNT = ("\ue004", "account")
    HUMAN_GREETING = ("\ue64a", "human-greeting")
    RUN = ("\ue70e", "run")
    POOL = ("\ue606", "pool")
    SHOWER = ("\ue9a0", "shower")
    SILVERWARE_FORK_KNIFE = ("\uea70", "silverware-fork-knife")
    SOFA = ("\ue4b9", "sofa")
    TOILET = ("\ue9ab", "toilet")
    LEAF = ("\ue32a", "leaf")

    # Time & Wireless
    CALENDAR = ("\ue0ed", "calendar")
    CLOCK_OUTLINE = ("\ue150", "clock-outline")
    HISTORY = ("\ue2da", "history")
    TIMER_OUTLINE = ("\ue51b", "timer-outline")
    BLUETOOTH = ("\ue0af", "bluetooth")
    WIFI = ("\ue5a9", "wifi")
    ALERT = ("\ue026", "alert")

    @property
    def unicode(self) -> str:
        """Returns the unicode value of the icon in mdi."""
        return self.value[0]

    @property
    def name(self) -> str:
        """Returns the name of the icon in mdi."""
        return self.value[1]

    @classmethod
    def entries(cls) -> List[Tuple[str, str]]:
        """
        Returns a list of tuples containing the unicode value and the name of icon in mdi.
        """
        return [(member.value[0], member.value[1]) for member in cls]
