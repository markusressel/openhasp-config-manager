# Integrating openhasp-config-manager into Home Assistant

The "standard" way of configuring actions based on events from your plates
is to use the [OpenHASP Home Assistant integration](https://github.com/HASwitchPlate/openHASP-custom-component).
This integration uses the Home Assistant configuration YAML files, where you can specify
devices and actions based on events received from a device.

While this works pretty well, it has some limitations:

1. Home Assistant needs to be restarted after a configuration change
2. The integration only supports service calls as actions
3. Integrating this into appdaemon is cumbersome because of the required boilerplate

To work around these, we can skip the integration entirely and simply "convert" any MQTT event we receive
from any of the OpenHASP plates into an Home Assistant "event". This event can then be used in automations as well
as appdaemon. Updates to the configuration of the plate are immediately propagated, so there is no need
to restart Home Assistant to make changes in automations or appdaemon work.

```yaml
alias: OpenHASP MQTT to Event Bridge
description: "Sends an event for each message received on the hasp/# topic, which can then be consumed by other automations or appdaemon."
trigger:
  - platform: mqtt
    topic: hasp/#
condition: [ ]
action:
  - event: custom.openhasp.mqtt_event
    event_data:
      topic: "{{ trigger.topic }}"
      payload: "{{ trigger.payload }}"
mode: queued
max: 10000
```
