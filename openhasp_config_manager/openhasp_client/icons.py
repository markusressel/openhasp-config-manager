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
    ARROW_DOWN = ("\uE045", "arrow-down")
    ARROW_DOWN_BOX = ("\uE6C0", "arrow-down-box")
    ARROW_LEFT = ("\uE04D", "arrow-left")
    ARROW_LEFT_BOX = ("\uE6C1", "arrow-left-box")
    ARROW_RIGHT = ("\uE054", "arrow-right")
    ARROW_RIGHT_BOX = ("\uE6C2", "arrow-right-box")
    ARROW_UP = ("\uE05D", "arrow-up")
    ARROW_UP_BOX = ("\uE6C3", "arrow-up-box")
    CHEVRON_DOWN = ("\uE140", "chevron-down")
    CHEVRON_LEFT = ("\uE141", "chevron-left")
    CHEVRON_RIGHT = ("\uE142", "chevron-right")
    CHEVRON_UP = ("\uE143", "chevron-up")
    SUBDIRECTORY_ARROW_LEFT = ("\uE60C", "subdirectory-arrow-left")

    # Energy & Battery
    BATTERY_HIGH = ("\uF2A3", "battery-high")
    BATTERY_LOW = ("\uF2A1", "battery-low")
    BATTERY_MEDIUM = ("\uF2A2", "battery-medium")
    BATTERY_OUTLINE = ("\uE08E", "battery-outline")
    EV_STATION = ("\uE5F1", "ev-station")
    LIGHTNING_BOLT = ("\uF40B", "lightning-bolt")
    POWER = ("\uE425", "power")
    POWER_PLUG = ("\uE6A5", "power-plug")
    SOLAR_PANEL = ("\uED9B", "solar-panel")
    SOLAR_PANEL_LARGE = ("\uED9C", "solar-panel-large")
    SOLAR_POWER = ("\uEA72", "solar-power")
    SOLAR_POWER_VARIANT_OUTLINE = ("\uFA74", "solar-power-variant-outline")
    TRANSMISSION_TOWER = ("\uED3E", "transmission-tower")
    TRANSMISSION_TOWER_EXPORT = ("\uF92C", "transmission-tower-export")
    TRANSMISSION_TOWER_IMPORT = ("\uF92D", "transmission-tower-import")

    # Climate & Weather
    AIR_CONDITIONER = ("\uE01B", "air-conditioner")
    CLOUD_SEARCH_OUTLINE = ("\uE957", "cloud-search-outline")
    FIRE = ("\uE238", "fire")
    RADIATOR = ("\uE438", "radiator")
    RADIATOR_DISABLED = ("\uEAD7", "radiator-disabled")
    RADIATOR_OFF = ("\uEAD8", "radiator-off")
    SNOWFLAKE = ("\uE717", "snowflake")
    THERMOMETER = ("\uE50F", "thermometer")
    WATER = ("\uE58C", "water")
    WATER_PERCENT = ("\uE58E", "water-percent")
    WEATHER_CLOUDY = ("\uE590", "weather-cloudy")
    WEATHER_FOG = ("\uE591", "weather-fog")
    WEATHER_HAIL = ("\uE592", "weather-hail")
    WEATHER_HAZY = ("\uEF30", "weather-hazy")
    WEATHER_LIGHTNING = ("\uE593", "weather-lightning")
    WEATHER_LIGHTNING_RAINY = ("\uE67E", "weather-lightning-rainy")
    WEATHER_NIGHT = ("\uE594", "weather-night")
    WEATHER_NIGHT_PARTLY_CLOUDY = ("\uEF31", "weather-night-partly-cloudy")
    WEATHER_PARTLY_CLOUDY = ("\uE595", "weather-partly-cloudy")
    WEATHER_POURING = ("\uE596", "weather-pouring")
    WEATHER_RAINY = ("\uE597", "weather-rainy")
    WEATHER_SNOWY = ("\uE598", "weather-snowy")
    WEATHER_SNOWY_RAINY = ("\uE67F", "weather-snowy-rainy")
    WEATHER_SUNNY = ("\uE599", "weather-sunny")
    WEATHER_WINDY = ("\uE59D", "weather-windy")
    WEATHER_WINDY_VARIANT = ("\uE59E", "weather-windy-variant")
    WHITE_BALANCE_SUNNY = ("\uE5A8", "white-balance-sunny")

    # Lighting
    CEILING_LIGHT = ("\uE769", "ceiling-light")
    COACH_LAMP = ("\uF020", "coach-lamp")
    DESK_LAMP = ("\uE95F", "desk-lamp")
    FLOOR_LAMP = ("\uE8DD", "floor-lamp")
    LAMP = ("\uE6B5", "lamp")
    LIGHTBULB = ("\uE335", "lightbulb")
    LIGHTBULB_ON = ("\uE6E8", "lightbulb-on")
    OUTDOOR_LAMP = ("\uF054", "outdoor-lamp")
    STRING_LIGHTS = ("\uF2BA", "string-lights")
    VANITY_LIGHT = ("\uF1E1", "vanity-light")
    WALL_SCONCE = ("\uE91C", "wall-sconce")

    # Controls & UI
    CHECK = ("\uE12C", "check")
    CLOSE = ("\uE156", "close")
    COG = ("\uE493", "cog")
    DOTS_VERTICAL = ("\uE1D9", "dots-vertical")
    MINUS = ("\uE374", "minus")
    PLUS = ("\uE415", "plus")
    PAUSE = ("\uE3E4", "pause")
    PLAY = ("\uE40A", "play")
    REPEAT = ("\uE456", "repeat")
    REPEAT_OFF = ("\uE457", "repeat-off")
    REPEAT_ONCE = ("\uE458", "repeat-once")
    SHUFFLE = ("\uE49D", "shuffle")
    SHUFFLE_DISABLED = ("\uE49E", "shuffle-disabled")
    SKIP_NEXT = ("\uE4AD", "skip-next")
    SKIP_PREVIOUS = ("\uE4AE", "skip-previous")
    STOP = ("\uE4DB", "stop")
    VOLUME_HIGH = ("\uE57E", "volume-high")
    VOLUME_MEDIUM = ("\uE580", "volume-medium")
    VOLUME_MUTE = ("\uE75F", "volume-mute")

    # Home & Security
    HOME = ("\uE2DC", "home")
    HOME_OUTLINE = ("\uE6A1", "home-outline")
    CCTV = ("\uE7AE", "cctv")
    DOOR_CLOSED = ("\uE81B", "door-closed")
    DOOR_CLOSED_LOCK = ("\uF0AF", "door-closed-lock")
    DOOR_OPEN = ("\uE81C", "door-open")
    GARAGE_OPEN_VARIANT = ("\uF2D4", "garage-open-variant")
    GARAGE_VARIANT = ("\uF2D3", "garage-variant")
    KEY_VARIANT = ("\uE30B", "key-variant")
    LOCK = ("\uE33E", "lock")
    LOCK_OPEN_VARIANT = ("\uEFC6", "lock-open-variant")
    SHIELD_CHECK = ("\uE565", "shield-check")
    SHIELD_HOME = ("\uE68A", "shield-home")
    SHIELD_LOCK = ("\uE99D", "shield-lock")
    BELL = ("\uE09A", "bell")

    # Household Objects & Devices
    BED = ("\uE2E3", "bed")
    CAR = ("\uE10B", "car")
    COFFEE = ("\uE176", "coffee")
    DISHWASHER = ("\uEAAC", "dishwasher")
    ENGINE = ("\uE1FA", "engine")
    FAN = ("\uE210", "fan")
    FOUNTAIN = ("\uE96B", "fountain")
    FRIDGE_OUTLINE = ("\uE28F", "fridge-outline")
    KETTLE = ("\uE5FA", "kettle")
    LAPTOP = ("\uE322", "laptop")
    MICROWAVE = ("\uEC99", "microwave")
    RECYCLE_VARIANT = ("\uF39D", "recycle-variant")
    ROBOT_MOWER_OUTLINE = ("\uF1F3", "robot-mower-outline")
    ROBOT_VACUUM = ("\uE70D", "robot-vacuum")
    STOVE = ("\uE4DE", "stove")
    TELEVISION = ("\uE502", "television")
    TRASH_CAN_OUTLINE = ("\uEA7A", "trash-can-outline")
    TUMBLE_DRYER = ("\uE917", "tumble-dryer")
    WASHING_MACHINE = ("\uE72A", "washing-machine")
    WATER_PUMP = ("\uE58F", "water-pump")
    MONITOR_SPEAKER = ("\uEF5F", "monitor-speaker")
    SPEAKER = ("\uE4C3", "speaker")
    CELLPHONE = ("\uE11C", "cellphone")
    MUSIC = ("\uE75A", "music")

    # Windows & Blinds
    BLINDS = ("\uE0AC", "blinds")
    BLINDS_OPEN = ("\uF011", "blinds-open")
    WINDOW_SHUTTER = ("\uF11C", "window-shutter")
    WINDOW_SHUTTER_ALERT = ("\uF11D", "window-shutter-alert")
    WINDOW_SHUTTER_OPEN = ("\uF11E", "window-shutter-open")
    WINDOW_CLOSED_VARIANT = ("\uF1DB", "window-closed-variant")

    # Presence & Misc
    ACCOUNT = ("\uE004", "account")
    HUMAN_GREETING = ("\uE64A", "human-greeting")
    RUN = ("\uE70E", "run")
    POOL = ("\uE606", "pool")
    SHOWER = ("\uE9A0", "shower")
    SILVERWARE_FORK_KNIFE = ("\uEA70", "silverware-fork-knife")
    SOFA = ("\uE4B9", "sofa")
    TOILET = ("\uE9AB", "toilet")
    LEAF = ("\uE32A", "leaf")

    # Time & Wireless
    CALENDAR = ("\uE0ED", "calendar")
    CLOCK_OUTLINE = ("\uE150", "clock-outline")
    HISTORY = ("\uE2DA", "history")
    TIMER_OUTLINE = ("\uE51B", "timer-outline")
    BLUETOOTH = ("\uE0AF", "bluetooth")
    WIFI = ("\uE5A9", "wifi")
    ALERT = ("\uE026", "alert")

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
