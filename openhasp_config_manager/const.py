COMMON_FOLDER_NAME = "common"
DEVICES_FOLDER_NAME = "devices"

# the longest name of a file on the plate (the flattened path, see README "Output file name length"): measured on openHASP
# 0.7.0-rc13 on an ESP32-S3, where 255 characters work and 256 are refused (LittleFS `LFS_NAME_MAX`)
PLATE_FILE_NAME_MAX = 255
# the key in the `openhasp_config_manager.device` section of a device's config.json that sets a lower limit for its plate, e.g. 31
# for an ESP8266
MAX_FILE_NAME_LENGTH_KEY = "max_file_name_length"

SYSTEM_SCRIPTS = ["boot.cmd", "online.cmd", "offline.cmd", "mqtt_off.cmd", "mqtt_on.cmd"]
