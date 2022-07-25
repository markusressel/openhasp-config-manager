import json
import re
from typing import List


class Processor:

    def process_jsonl(self, original_content: str) -> str:
        return self._normalize_jsonl(original_content)

    def _normalize_jsonl(self, original_content: str) -> str:
        parts = self._split_jsonl_objects(original_content)
        normalized_parts: List[str] = []
        for part in parts:
            p = json.dumps(json.loads(part), indent=None)
            normalized_parts.append(p)

        return "\n".join(normalized_parts)

    @staticmethod
    def _split_jsonl_objects(original_content: str) -> List[str]:
        pattern_to_find_beginning_of_objects = re.compile(r'^(?!\n)\s*(?=\{)', re.RegexFlag.MULTILINE)
        parts = pattern_to_find_beginning_of_objects.split(original_content)

        result = []
        for part in parts:
            part = part.strip()

            # edge case for first match
            if "}" not in part:
                continue

            # ignore lines starting with "//"
            part = "\n".join([line for line in part.splitlines() if not line.strip().startswith("//")])

            # ignore everything after the last closing bracket
            part = part.rsplit("}", maxsplit=1)[0] + "}"

            result.append(part)

        return result
