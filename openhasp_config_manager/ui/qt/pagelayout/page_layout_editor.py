import asyncio
from collections import OrderedDict
from typing import List, Dict, Set, Optional

from PyQt6 import QtCore
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from orjson import orjson

from openhasp_config_manager.manager import ConfigManager
from openhasp_config_manager.openhasp_client.openhasp import OpenHaspClient
from openhasp_config_manager.ui.components import UiComponents
from openhasp_config_manager.ui.dimensions import UiDimensions
from openhasp_config_manager.ui.qt.pagelayout import OpenHaspDevicePagesData
from openhasp_config_manager.ui.qt.pagelayout.jsonl_preview import PageJsonlPreviewWidget
from openhasp_config_manager.ui.qt.pagelayout.page_preview_layout import PagePreviewWidget2
from openhasp_config_manager.ui.qt.util import clear_layout, qBridge, run_async


class PageLayoutEditorWidget(QWidget):
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.device_processor = None
        # map of <json component name, list of objects>
        self.jsonl_component_objects: OrderedDict[str, List[Dict]] = OrderedDict()

        self.device_pages_data = None
        self.current_index = 1

        self.create_layout()

    def create_layout(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.layout.setSpacing(UiDimensions.one)

        self.preview_container = QWidget()
        self.preview_container.setLayout(UiComponents.create_column())
        self.layout.addWidget(self.preview_container)

        self.page_selector = self._create_page_selector()
        self.layout.addWidget(self.page_selector)

    def _on_previous_page_clicked(self):
        self.previous_page_index()

    def _on_next_page_clicked(self):
        self.next_page_index()

    def clear(self):
        clear_layout(self.preview_container.layout())
        self.current_index = 1
        self.jsonl_component_objects.clear()

    def set_data(self, device_pages_data: Optional[OpenHaspDevicePagesData]):
        self.device_pages_data = device_pages_data
        self.clear()
        if device_pages_data is None:
            return
        self.device_processor = self.config_manager.create_device_processor(device_pages_data.device)

        # load jsonl component objects
        for jsonl_component in self.device_pages_data.jsonl_components:
            normalized_jsonl_component = self.device_processor.normalize(self.device_pages_data.device, jsonl_component)
            objects_in_jsonl = normalized_jsonl_component.splitlines()
            loaded_objects = list(map(orjson.loads, objects_in_jsonl))
            self.jsonl_component_objects[jsonl_component.name] = loaded_objects

        self.page_preview_widget = PagePreviewWidget2(device_pages_data, [])
        self.page_preview_widget.clickedValue.connect(lambda value: print(f"Clicked at value: {value}"))
        self.page_preview_widget.buttonClicked.connect(self.__on_preview_layout_button_clicked)
        self.preview_container.layout().addWidget(self.page_preview_widget)

        self.page_jsonl_preview = PageJsonlPreviewWidget(device_pages_data)
        self.preview_container.layout().addWidget(self.page_jsonl_preview)

        self.button_clear_page = UiComponents.create_button(
            title="Clear Page",
            on_click=self._on_clear_page_clicked
        )
        self.preview_container.layout().addWidget(self.button_clear_page)
        self.button_clear_page.clicked.connect(self._on_clear_page_clicked)

        self.button_deploy_page = UiComponents.create_button(
            title="Deploy Page",
            on_click=self._on_deploy_page_clicked
        )
        self.preview_container.layout().addWidget(
            self.button_deploy_page
        )

        self.button_deploy_page.clicked.connect(self._on_deploy_page_clicked)

        self.set_page_index(index=1)

    @qBridge(dict)
    def __on_preview_layout_button_clicked(self, obj: dict):
        print(f"Clicked on object in preview: {obj}")
        action = obj.get("action", None)

        if action in ("next", "prev", "back"):
            if action == "next":
                self.next_page_index()
            elif action == "prev":
                self.previous_page_index()
            elif action == "back":
                self.go_to_home_page()

            async def __async_work():
                # switch the device to this page
                device = self.device_pages_data.device
                client = OpenHaspClient(device)
                await client.set_page(self.current_index)

            run_async(
                coro=__async_work(),
            )

    @qBridge()
    def _on_clear_page_clicked(self):
        """
        Clear the current page index on the device.
        """
        if self.current_index is None:
            return

        self.button_clear_page.setEnabled(False)

        device = self.device_pages_data.device
        current_index = self.current_index

        print(f"Clearing page {self.current_index} on device {device.name}")
        client = OpenHaspClient(device)

        async def __async_work():
            await client.clear_page(current_index)

        def __on_done():
            self.button_clear_page.setEnabled(True)

        run_async(
            coro=__async_work(),
            on_done=__on_done,
        )

    @qBridge()
    def _on_deploy_page_clicked(self):
        """
        Deploy the current page index to the device.
        """
        if self.page_objects is None or len(self.page_objects) == 0:
            return

        self.button_deploy_page.setEnabled(False)

        device = self.device_pages_data.device
        current_index = self.current_index
        page_objects = self.get_page_objects(index=current_index, include_global=True)

        print(f"Deploying page {self.current_index} to device {device.name}")
        client = OpenHaspClient(device)

        async def __async_work():
            # clear the page first
            print(f"Clearing page {current_index}")
            await client.clear_page(current_index)

            print(f"Sending {len(page_objects)} on page {current_index} to device {device.name}")
            # send all objects for the current page index
            for obj in page_objects:
                await client.jsonl(obj)
                await asyncio.sleep(0.1)  # small delay to avoid overwhelming the device

        def __on_done():
            print(f"Finished deploying page {current_index} to device {device.name}")
            self.button_deploy_page.setEnabled(True)

        run_async(
            coro=__async_work(),
            on_done=__on_done,
        )

    def go_to_home_page(self):
        usable_page_indices = self.get_navigable_page_indices()
        if len(usable_page_indices) == 0:
            return
        self.set_page_index(usable_page_indices[0])

    def set_page_index(self, index: int):
        print("Setting page index", index)
        self.current_index = index
        self.page_objects = self.get_page_objects(index=index)
        print(f"Page objects: {self.page_objects}")
        self.page_preview_widget.set_objects(self.page_objects)

        self.page_jsonl_preview.set_objects(self.page_objects)

    def next_page_index(self):
        """
        Cycle to the next available page index, skipping page 0 and rolling over to the first page.
        """
        usable_page_indices = self.get_navigable_page_indices()
        current_page_index_position_in_set = usable_page_indices.index(self.current_index)
        new_page_index_position_in_set = (current_page_index_position_in_set + 1) % len(usable_page_indices)
        self.set_page_index(usable_page_indices[new_page_index_position_in_set])

    def previous_page_index(self):
        """
        Cycle to the previous available page index, skipping page 0 and rolling over to the last page.
        """
        usable_page_indices = self.get_navigable_page_indices()
        current_page_index_position_in_set = usable_page_indices.index(self.current_index)
        new_page_index_position_in_set = (current_page_index_position_in_set - 1) % len(usable_page_indices)
        self.set_page_index(usable_page_indices[new_page_index_position_in_set])

    def get_navigable_page_indices(self) -> List[int]:
        usable_page_indices = self.get_used_page_indices() - {0}
        return list(sorted(usable_page_indices))

    def get_used_page_indices(self) -> Set[int]:
        """
        Get the used page indices from the jsonl component objects.
        :return: a list of used page indices
        """
        if self.device_pages_data is None:
            return set()

        used_page_indices = set()
        for jsonl_component_name, objects_in_jsonl in self.jsonl_component_objects.items():
            for obj in objects_in_jsonl:
                object_page_index = obj.get("page", None)
                if object_page_index is not None:
                    used_page_indices.add(object_page_index)

        print(f"Used page indices: {used_page_indices}")

        return used_page_indices

    def get_page_objects(self, index: int, include_global: bool = True) -> List[dict]:
        """
        Get the page objects for the given page index.
        :param index: the index of the page
        :return: a list of objects for the page
        """
        if self.device_pages_data is None:
            return []

        result = []
        for jsonl_component_name, objects_in_jsonl in self.jsonl_component_objects.items():
            result = result + objects_in_jsonl

        # Filter the objects based on the index
        result = [
            obj for obj in result if
            obj.get("page") == index or (obj.get("page") == 0 if include_global else False)
        ]

        # Filter hidden objects
        result = [obj for obj in result if not obj.get("hidden", False)]

        # Draw objects on page 0 last (on top)
        result.sort(key=lambda obj: obj.get("page") == 0)

        return result

    def _create_page_selector(self) -> QWidget:
        page_selector_widget = QWidget()
        page_selector_widget.setLayout(UiComponents.create_row())

        self._previous_page_button_widget = UiComponents.create_button(
            title="Previous Page",
            on_click=self._on_previous_page_clicked
        )
        page_selector_widget.layout().addWidget(self._previous_page_button_widget)

        self._next_page_button_widget = UiComponents.create_button(
            title="Next Page",
            on_click=self._on_next_page_clicked,
        )
        page_selector_widget.layout().addWidget(self._next_page_button_widget)

        return page_selector_widget

    def get_page_index(self) -> int:
        return self.current_index
