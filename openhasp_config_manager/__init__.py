import json
import re
from pathlib import Path
from typing import List

from openhasp_config_manager.model import Component, Page, WebserverConfig, Device
from openhasp_config_manager.openhasp import upload_file


def analyze_component(component_path: Path) -> Component:
    index, name = component_path.name.split("_")

    return Component(
        name=name.removesuffix(".jsonl"),
        index=int(index),
        path=component_path,
    )


def analyze_page(page_path: Path) -> Page:
    components: List[Component] = []

    for component_file in page_path.glob("*.jsonl"):
        if not component_file.is_file():
            continue

        component = analyze_component(component_file)
        components.append(component)

    index, name = page_path.name.split("_")

    return Page(
        name=name,
        index=int(index),
        path=page_path,
        components=components,
    )


def analyze_device(device_cfg_dir_root: Path) -> List[Page]:
    result: List[Page] = []

    pages_path = Path(device_cfg_dir_root, "pages")
    for page_path in pages_path.iterdir():
        if not page_path.is_dir():
            continue

        page = analyze_page(page_path)
        result.append(page)

    return result


def read_webserver_config(device_path: Path) -> WebserverConfig | None:
    credentials_path = Path(device_path, "config.json")
    if credentials_path.exists() and credentials_path.is_file():
        content = credentials_path.read_text()
        loaded = json.loads(content)
        return WebserverConfig(
            loaded["website"],
            loaded["user"],
            loaded["password"]
        )


def analyze(cfg_dir_root: Path, output_dir_root: Path) -> List[Device]:
    result: List[Device] = []

    # TODO: handle common components
    common_components_path = Path(cfg_dir_root, "common")

    devices_path = Path(cfg_dir_root, "devices")
    for device_path in devices_path.iterdir():
        if not device_path.is_dir():
            continue

        pages = analyze_device(device_path)
        webserver = read_webserver_config(device_path)
        device_output_dir = Path(output_dir_root, device_path.name)

        device = Device(
            path=device_path,
            name=device_path.name,
            pages=pages,
            webserver=webserver,
            output_dir=device_output_dir,
        )

        result.append(device)

    return result


def normalize_jsonl(original_content: str) -> str:
    pattern_to_find_beginning_of_objects = re.compile(r'^(?!\n)\s*(?=\{)', re.RegexFlag.MULTILINE)

    parts = pattern_to_find_beginning_of_objects.split(original_content)
    normalized_parts: List[str] = []
    for part in parts:
        part = part.strip()

        # edge case for first match
        if "}" not in part:
            continue

        # ignore lines starting with "//"
        part = "\n".join([line for line in part.splitlines() if not line.strip().startswith("//")])

        # ignore everything after the last closing bracket
        part = part.rsplit("}", maxsplit=1)[0] + "}"

        p = json.dumps(json.loads(part), indent=None)
        normalized_parts.append(p)

    return "\n".join(normalized_parts)


def generate_component_output(component: Component, component_output_file: Path):
    original_content = component.path.read_text()
    normalized = normalize_jsonl(original_content)
    component_output_file.write_text(normalized)


def generate_page_output(page: Page, page_output_dir: Path):
    for component in page.components:
        component_output_file = Path(
            page_output_dir,
            f"{page.index}_{page.name}__{component.index}_{component.name}.jsonl"
        )
        page_output_dir.mkdir(parents=True, exist_ok=True)
        generate_component_output(component, component_output_file)


def generate_device_output(device: Device):
    # *.cmd files in device root
    for root_file in device.path.glob("*.cmd"):
        original_content = root_file.read_text()
        output_file = Path(device.output_dir, root_file.name)
        output_file.write_text(original_content)

    # device-specific common files
    common_path = Path(device.path, "common")
    for common_file in common_path.glob("*.jsonl"):
        original_content = common_file.read_text()
        output_file = Path(device.output_dir, common_file.name)
        normalized = normalize_jsonl(original_content)
        output_file.write_text(normalized)

    # page-specific files for this device
    for page in device.pages:
        page_output_dir = Path(device.output_dir)
        generate_page_output(page, page_output_dir)


def generate_output(cfg_root_dir: Path, output_root_dir: Path, devices: List[Device]):
    # global common files
    src_common_path = Path(cfg_root_dir, "common")

    output_common_path = Path(output_root_dir, "common")
    output_common_path.mkdir(parents=True, exist_ok=True)

    for common_file in src_common_path.glob("*.jsonl"):
        original_content = common_file.read_text()
        normalized = normalize_jsonl(original_content)
        output_file = Path(output_common_path, common_file.name)
        output_file.write_text(normalized)

    # Device specific files

    for device in devices:
        print(f"Generating output files for device '{device.name}'...")

        # write global common files to device specific output (?)
        for common_file in output_common_path.iterdir():
            content = common_file.read_text()
            Path(device.output_dir, common_file.name).write_text(content)

        generate_device_output(device)

def upload_files(device: Device):
    for file in device.output_dir.iterdir():
        content = file.read_text()
        upload_file(device, file.name, content)


if __name__ == '__main__':
    cfg_dir_root = Path("../openhasp-configs")
    output_dir_root = Path("../output")

    print(f"Analyzing config files in '{cfg_dir_root}'...")
    devices = analyze(cfg_dir_root, output_dir_root)

    common_path = Path(cfg_dir_root, "common")
    generate_output(cfg_dir_root, output_dir_root, devices)

    for device in devices:
        print(f"Uploading files to device '{device.name}'...")
        # upload_files(device)

    print(devices)

    # TODO: naming clashes can still happen and there is no warning about them
