# Integrating `openhasp-config-manager` into Home Assistant

The traditional way to handle plate events is through the [OpenHASP Home Assistant integration](https://github.com/HASwitchPlate/openHASP-custom-component).
While this standard YAML-based approach is functional, it introduces several bottlenecks for advanced setups.

### Limitations of the Standard Integration

* **Mandatory Restarts:** Most configuration changes require a Home Assistant restart, or at least a configuration reload to take effect.
* **Service Call Limits:** The integration is primarily designed around service calls, which can be restrictive for complex logic.
* **AppDaemon Friction:** Using the standard integration with [AppDaemon](https://github.com/AppDaemon/appdaemon) involves significant boilerplate code, making the workflow
  cumbersome.

---

## Option A: Using the OpenHaspClient

The `OpenHaspClient` included in `openhasp-config-manager` can be used to directly connect to the MQTT broker and listen for messages, bypassing Home Assistant's MQTT integration
entirely.
This allows for even more direct control and can be particularly useful for complex logic or when you want to avoid any potential latency introduced by Home Assistant's event
system.
More generally speaking, this is entirely independent of Home Assistant and can be used in any Python environment, making it a versatile choice for various applications beyond just
Home Assistant.

### 
Using `openhasp-config-manager` as a library in an AppDaemon setup is very simple. Create a `requirements.txt` file in your AppDaemon directory with the following content:

```
openhasp-config-manager==0.7.0
```

When starting the AppDaemon Docker container, it will automatically install the required package from PyPI.
Then, in your AppDaemon app, you can import and use the `OpenHaspClient` like this:

```python
from openhasp_config_manager import OpenHaspClient
```

I have already written extensive tooling to make it easy to integrate OpenHASP into AppDaemon, 
but at the moment it is still a work in progress and not published into its own library.

## Option B: MQTT-to-Event Bridge

By skipping the custom integration and "bridging" MQTT messages directly into Home Assistant **Events**, (which can easily be listened to from within AppDaemon) you create
a more flexible and responsive system.

This bridge converts any message from the `hasp/#` topic into a `custom.openhasp.mqtt_event`. This event can be monitored by any automation or AppDaemon app, allowing for real-time
updates without cycling the Home Assistant core.

#### The Bridge Automation

Add the following automation to your Home Assistant instance. It uses `queued` mode with a high `max` value to ensure no button presses or state updates are missed during
high-traffic bursts.

```yaml
alias: OpenHASP MQTT to Event Bridge
description: "Sends an event for each message received on the hasp/# topic, which can then be consumed by other automations or appdaemon."
trigger:
  - platform: mqtt
    topic: hasp/#
action:
  - event: custom.openhasp.mqtt_event
    event_data:
      topic: "{{ trigger.topic }}"
      payload: "{{ trigger.payload }}"
mode: queued
max: 10000
```
