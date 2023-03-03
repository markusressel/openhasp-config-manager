import re
from typing import List


class JsonlPreProcessor:

    def __init__(self):
        pass

    def split_jsonl_objects(self, original_content: str) -> List[str]:
        pattern_to_find_beginning_of_objects = re.compile(r'^(?!\n)\s*(?=\{)', re.RegexFlag.MULTILINE)
        parts = pattern_to_find_beginning_of_objects.split(original_content)

        result = []
        for part in parts:
            part = part.strip()

            # edge case for first match
            if "}" not in part:
                continue

            # ignore everything after the last closing bracket
            part = part.rsplit("}", maxsplit=1)[0] + "}"

            result.append(part)

        return result

    def cleanup_object_for_json_parsing(self, content: str) -> str:
        """
        Prepares the given content for json parsing (if possible)
        :param content: original content
        :return: cleaned up content
        """
        return self.remove_comments(content)

    def remove_comments(self, content: str) -> str:
        """
        Removes comments indicated by "//"
        :param content: original content
        :return: modified content without comments
        """
        result_lines1 = [line for line in content.splitlines() if not line.strip().startswith("//")]

        result_lines2 = []
        for line in result_lines1:
            if line.strip().startswith("//"):
                continue

            parts = re.split("(?!,)(\s*//.*)$", line)
            parts = [part.strip() for part in parts if len(part.strip()) > 0]
            keep = parts[0:max(1, len(parts) - 1)]

            line = "".join(keep)
            result_lines2.append(line)

        result = "\n".join(result_lines2)
        return result
