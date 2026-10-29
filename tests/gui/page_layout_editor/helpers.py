"""Helpers of the tests of the page layout editor."""

import threading




EDITOR_JSONL = """{"page": 9, "id": 1, "obj": "label", "text": "A", "x": 10}
{"page": 9, "id": 2, "obj": "btn", "text": "B"}
{"page": 1, "id": 50, "obj": "label", "text": "E"}
"""


class _Plate:
    """Records what the editor sends to the plate (from the background loop)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._calls = []

    def record(self, *call):
        with self._lock:
            self._calls.append(call)

    @property
    def calls(self):
        with self._lock:
            return list(self._calls)

    def clear(self):
        with self._lock:
            self._calls.clear()


def _sent_objects(plate: _Plate):
    return [(call[1].get("page"), call[1].get("id")) for call in plate.calls if call[0] == "jsonl"]


def _object(editor, obj_id: int):
    return next(obj for obj in editor.page_objects if obj.get("page") == 9 and obj.get("id") == obj_id)


def _key(editor, file_name: str) -> str:
    return next(component.key for component in editor.session.components if component.path.name == file_name)


DOT_JSONL = '{"page": 9, "id": "{{ id }}", "obj": "label", "x": "{{ id * 10 }}", "text": "{{ prefix }}{{ id }}"}\n'


DOT_INCLUDE = '{"!include": "common/parts/dot.jsonl", "vars": {"prefix": ""}, "for": {"id": [20, 21]}}\n'
