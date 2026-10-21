from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class Theme:
    """
    Default properties of code-defined objects, the counterpart of `theme.obj.*` in `theme.yaml` for JSONL files.

    Fonts and images referenced here (`text_font`, `src="L:/..."`) must already be on the plate's flash: haad does not
    upload them, they come from the deployment with openhasp-config-manager.
    """

    # the background of every owned page (`bg_color` of p<N>b0)
    background_color: str = "#000000"
    # per openHASP object type ("btn", "label", "switch", "bar", ...): defaults applied to every object of that type, unless
    # the object sets the property itself (the same rule as ObjectThemeProcessor applies to theme.obj.* for JSONL files)
    obj: Mapping[str, Mapping[str, Any]] = field(default_factory=lambda: MappingProxyType({}))

    def defaults_for(self, obj_type: str) -> Mapping[str, Any]:
        """The theme's default properties of an object type."""
        return self.obj.get(obj_type, {})
