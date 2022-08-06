import json

from py_range_parse import Range


class JsonlObjectValidator:

    def validate(self, data: str):
        for line in data.splitlines():
            input = json.loads(line)

            if "id" in input.keys():
                value = input["id"]
                valid_range = Range(0, 254)
                if not isinstance(value, int) or value not in valid_range:
                    raise AssertionError(f"Object has invalid id '{value}', must be in range: {valid_range}")
