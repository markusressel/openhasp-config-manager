import json

from py_range_parse import Range


class JsonlObjectValidator:

    def __init__(self):
        self._seen_ids = {}

    def validate(self, data: str):
        for line in data.splitlines():
            input = json.loads(line)
            self._validate_object(input)

    def _validate_object(self, input):
        input_page = input.get("page", None)
        input_id = input.get("id", None)
        self.__remember_page_id_combo(input_page, input_id)

        if input_id is not None:
            valid_range = Range(0, 254)
            if not isinstance(input_id, int) or input_id not in valid_range:
                raise AssertionError(f"Object has invalid id '{input_id}', must be in range: {valid_range}")

        input_align = input.get("align", None)
        if input_align is not None:
            if isinstance(input_align, str):
                if input_align not in ["left", "center", "right"]:
                    raise AssertionError(f"Invalid 'align' value: {input_align}")
            if isinstance(input_align, int):
                if input_align not in [0, 1, 2]:
                    raise AssertionError(f"Invalid 'align' value: {input_align}")

    def __remember_page_id_combo(self, input_page: int, input_id: int):
        key = f"p{input_page}b{input_id}"
        if key in self._seen_ids.keys():
            raise AssertionError(f"Duplicate id detected: {key}")
        else:
            self._seen_ids[key] = True
