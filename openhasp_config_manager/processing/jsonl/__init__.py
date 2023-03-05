import abc
from typing import Dict

from openhasp_config_manager.openhasp_client.model.config import Config


class JsonlObjectProcessor(metaclass=abc.ABCMeta):
    """
    Used to process .jsonl files to add support for additional features.
    """

    @abc.abstractmethod
    def process(self, input: Dict, config: Config) -> Dict:
        raise NotImplementedError
