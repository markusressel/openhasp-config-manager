from openhasp_config_manager.validation import Validator


class CmdFileValidator(Validator):

    def validate(self, content: str):
        for line in content.splitlines():
            line = line.lstrip()
            self._validate_line(line)

    def _validate_line(self, line):
        pass
