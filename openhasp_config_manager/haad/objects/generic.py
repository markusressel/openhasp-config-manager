from openhasp_config_manager.haad.objects import ObjectController


class GenericObjectController(ObjectController):
    """
    Any openHASP object type without a dedicated controller (`obj`, `arc`, `line`, `roller`, ...), see
    PageController.add_object(). Its properties are set with set_object_properties().
    """

    def __init__(self, *args, obj_type: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._obj_type = obj_type

    @property
    def obj_type(self) -> str:
        return self._obj_type

    async def init(self):
        pass
