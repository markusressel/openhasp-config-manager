from pathlib import Path

from appdaemon import ADAPI

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.processing.variables import VariableManager
from openhasp_config_manager.uploader import ConfigUploader


class DeploymentController:
    """
    Controller for the deployment of the OpenHASP configuration.
    """

    def __init__(self, app: ADAPI, name: str):
        self.app = app
        self._name = name

        self.config_dir = Path("/conf/openhasp-configs")
        self.output_dir = Path("/conf/openhasp-configs.output")

        variable_manager = VariableManager(cfg_root=self.config_dir)
        self._config_manager = ConfigManager(
            cfg_root=self.config_dir,
            output_root=self.output_dir,
            variable_manager=variable_manager,
        )

        self._analyze_and_filter(self._name)

    def _analyze_and_filter(self, device_filter: str = None):
        devices = self._config_manager.analyze()
        self.device = next(filter(lambda x: x.name == device_filter, devices))
        self.client = OpenHaspClient(device=self.device)
        self._uploader = ConfigUploader(self.output_dir, self.client)

    async def deploy(self, purge: bool = False, show_diff: bool = False) -> bool:
        """
        Deploys the openhasp-config-manager configuration for this device
        :param purge: if true, all objects not defined in the configuration will be removed
        :param show_diff: if true, the diff between the current and the new configuration will be shown
        :return: true if the configuration was changed, false otherwise
        """
        self.app.log(f"DEPLOY: Deploying configuration of {self.device.name}...")

        devices = self._config_manager.analyze()
        device_names = list(map(lambda x: x.name, devices))
        self.app.log(f"DEPLOY: Analysis finished, found: {', '.join(device_names)}, processing...")
        self.device = next(filter(lambda x: x.name == self._name, devices))
        self.app.log(f"DEPLOY: Device is: {self.device.name}, processing...")
        self._config_manager.process(self.device)
        self.app.log(f"DEPLOY: Finished processing {self.device.name}, uploading files...")
        changed = self._uploader.upload(self.device, purge, show_diff)
        self.app.log(f"DEPLOY: {self.device.name} Done! Changed: {changed}")
        return changed

    def deploy_config(self):
        self.client.set_gui_config(
            config=self.device.config.gui,
        )
        # await self.set_gui_config(
        #     idle1=self._device.config.gui.idle1,
        #     idle2=self._device.config.gui.idle2,
        # )
