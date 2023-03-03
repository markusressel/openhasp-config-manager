from typing import Dict

import orjson as orjson
from py_range_parse import Range

from openhasp_config_manager.validation import Validator


class JsonlObjectValidator(Validator):
    """
    Validates JSONL object definitions.
    """

    def __init__(self):
        self._seen_ids = {}

    def validate(self, data: str):
        for line in data.splitlines():
            input = orjson.loads(line)
            self._validate_object(input)

    def _validate_object(self, input: Dict):
        input_page = input.get("page", None)
        input_id = input.get("id", None)
        self.__remember_page_id_combo(input_page, input_id, input)

        if input_id is not None:
            valid_range = Range(0, 254)
            if not isinstance(input_id, int) or input_id not in valid_range:
                raise AssertionError(f"Object has invalid id '{input_id}', must be in range: {valid_range}")

        input_align = input.get("align", None)
        if input_align is not None:
            valid_align_int_values = [0, 1, 2]
            valid_align_str_values = ["left", "center", "right"]
            valid_align_values = valid_align_str_values + valid_align_int_values

            if input_align not in valid_align_values:
                if isinstance(input_align, str):
                    raise AssertionError(
                        f"Invalid 'align' string value: '{input_align}', must be one of: {valid_align_values}")
                if isinstance(input_align, int):
                    raise AssertionError(
                        f"Invalid 'align' integer value: '{input_align}', must be one of: {valid_align_values}")

    def __remember_page_id_combo(self, input_page: int, input_id: int, data: Dict):
        if input_page is None or input_id is None:
            raise AssertionError(f"page or id is None: {input_page}, {input_id}")

        key = f"p{input_page}b{input_id}"
        if key in self._seen_ids.keys():
            raise AssertionError(f"Duplicate id detected: {key}, already seen in object: {self._seen_ids[key]}")
        else:
            self._seen_ids[key] = data
