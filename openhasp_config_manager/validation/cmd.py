import orjson

from openhasp_config_manager.validation import Validator


class CmdFileValidator(Validator):

    def validate(self, data: str):
        for line in data.splitlines():
            line = line.lstrip()
            self._validate_line(line)

    def _validate_line(self, line: str):
        if line.startswith("run"):
            pass
        elif line.startswith("jsonl"):
            command, arg = line.split(sep=" ", maxsplit=1)
            try:
                import json
                orjson.loads(arg)
            except Exception as ex:
                raise AssertionError(f"jsonl command argument cannot be parsed: {ex}")
