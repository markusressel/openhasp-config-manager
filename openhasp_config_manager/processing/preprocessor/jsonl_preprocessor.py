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
        result = self._remove_comments(content).strip()
        result = self._remove_trailing_comma_of_last_property(result)
        return result

    def _remove_comments(self, content: str) -> str:
        """
        Removes comments indicated by "//"
        :param content: original content
        :return: modified content without comments
        """
        result_lines = []
        for line in content.splitlines():
            quote_count = 0
            new_line = []
            i = 0
            while i < len(line):
                char = line[i]
                if char == '"':
                    quote_count += 1
                if char == '/' and i + 1 < len(line) and line[i + 1] == '/' and quote_count % 2 == 0:
                    break
                new_line.append(char)
                i += 1
            cleaned_line = "".join(new_line).strip()
            if cleaned_line:  # Only append non-empty lines
                result_lines.append(cleaned_line)
        result = "\n".join(result_lines)
        return result.strip()

    def _remove_trailing_comma_of_last_property(self, content: str) -> str:
        """
        Removes the "," of the last property within the object.
        :param content: original content
        :return: modified content
        """
        result = content
        matches = re.findall(r",\s*}", content, flags=re.MULTILINE)
        if matches is not None:
            for match in matches:
                result = result.replace(match, match[1:])

        return result
