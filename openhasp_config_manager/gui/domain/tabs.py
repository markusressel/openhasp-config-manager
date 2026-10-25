"""Which `tab` objects belong to a `tabview`. Qt-free."""

from typing import Dict, List, Optional


def tab_texts(objects: List[Dict], tabview: Dict) -> List[str]:
    """:return: the texts of the tab buttons of a tabview, in the order of its tab objects (those on the same page that have it as parent)"""
    return [
        str(obj.get("text", "Tab"))
        for obj in objects
        if obj.get("obj") == "tab" and obj.get("page") == tabview.get("page") and obj.get("parentid") == tabview.get("id")
    ]


def last_tabview_id(objects: List[Dict], page: int) -> Optional[int]:
    """:return: the id of the tabview that was added last on a page, None if the page has none"""
    ids = [obj.get("id") for obj in objects if obj.get("obj") == "tabview" and obj.get("page") == page]
    return ids[-1] if ids else None
