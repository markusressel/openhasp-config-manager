# AppDaemon Integration Utils

This package contains utilities to integrate OpenHASP with AppDaemon, a popular Python-based automation framework for Home Assistant.
These utilities are designed to simplify the process of connecting to the MQTT broker, subscribing to relevant topics, and handling incoming messages in a way that
is efficient and easy to use within AppDaemon apps.

## Requirements

### AppDaemon Environment

Besides making sure AppDaemon is properly set up and running (which is already the case
if you use the AppDaemon Docker Container), make sure to include the `openhasp-config-manager` package in your AppDaemon environment. 
You can do this by adding it to your `requirements.txt` file:

**requirements.txt**
```requirements
openhasp-config-manager==0.7.0
```

## Implement a Plate within AppDaemon

#### 1. Define your Page(s)

Extend PageController and use the register_objects method to define your buttons, labels, and callbacks.

To create your own plate, you need to extend OpenHaspController and implement the setup_plate method. You can also define your UI layout (pages and objects) within this class.

```python
from typing import Dict

from appdaemon.plugins import hass

from openhasp_config_manager.ad.controller import OpenHaspController
from openhasp_config_manager.ad.page import PageController


class MyPlatePage(PageController):
  """Example of a custom page controller. You can create multiple pages and switch between them as needed."""

  async def register_objects(self):
    await super().register_objects()

    async def __callback(topic: str, payload: Dict):
      await self.plate.reboot()

      # Example "Reboot" Button
      await self.add_button(
        obj_id=50,
        on_click=__callback,
      )
```

#### 2. Register the Page in your Controller

Attach the custom page to your main OpenHaspController implementation.

```python
from appdaemon.plugins import hass

from openhasp_config_manager.ad.controller import OpenHaspController


class MyPlateController(OpenHaspController, hass.Hass):

  async def setup_plate(self):
    """Logic to run when the plate comes online."""

    # Initialize and add your custom page (index 1)
    main_page = MyPlatePage(app=self, index=1)
    self.add_page(main_page)

    self.log(f"Plate {self._name} UI initialized with custom page logic.")
```

### Key Workflow

1. `OpenHaspController`: Manages the connection lifecycle (LWT, online checks, and syncing).
2. `PageController`: Manages the specific layout and interaction of a single screen.
3. `register_objects`: The standard hook to instantiate your UI components once the connection is ready.