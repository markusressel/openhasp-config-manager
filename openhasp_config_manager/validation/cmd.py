class CmdFileValidator:

    def validate(self, content: str):
        for line in content.splitlines():
            line = line.lstrip()
            self._validate_line(line)

    def _validate_line(self, line):
        pass
