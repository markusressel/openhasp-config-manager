import re

import qtawesome as qta

from openhasp_config_manager.openhasp_client.icons import IntegratedIcon


class IconManager:
    @staticmethod
    def get_mdi_char(icon_name: str) -> str:
        """Fetch the character from the QtAwesome MDI library."""
        try:
            # We use 'mdi6' for newer Material Design Icons
            return qta.charmap(f"mdi6.{icon_name}")
        except Exception:
            return "?"


def parse_icons(text: str) -> str:
    for unicode_char, icon_name in IntegratedIcon.entries():
        # Get the actual character QtAwesome expects for this name
        icon_char = IconManager.get_mdi_char(icon_name)

        # Replace both the :name: shorthand and the OpenHASP unicode char
        text = text.replace(f":{icon_name}:", icon_char)
        text = text.replace(unicode_char, icon_char)

    # also replace every icon supported by the mdi6 set, using the :name: syntax
    # This allows users to use any mdi6 icon without it being explicitly listed in IntegratedIcon
    # We can identify mdi6 icons by the pattern :mdi6.name:
    pattern = r":mdi6\.([a-z0-9_-]+):"

    def replace_mdi6_icon(match):
        full_name = match.group(1)  # e.g., "mdi6.home"
        icon_char = IconManager.get_mdi_char(full_name)
        return icon_char

    text = re.sub(pattern, replace_mdi6_icon, text)

    return text
