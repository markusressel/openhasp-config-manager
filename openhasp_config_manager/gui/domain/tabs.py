"""Which `tab` objects belong to a `tabview`, and which objects are on a tab. Qt-free."""

from typing import Dict, List, Optional


def tab_objects(objects: List[Dict], tabview: Dict) -> List[Dict]:
    """:return: the tab objects of a tabview (those on the same page that have it as parent), in their order"""
    return [
        obj
        for obj in objects
        if obj.get("obj") == "tab" and obj.get("page") == tabview.get("page") and obj.get("parentid") == tabview.get("id")
    ]


def tab_texts(objects: List[Dict], tabview: Dict) -> List[str]:
    """:return: the texts of the tab buttons of a tabview, in the order of its tab objects"""
    return [str(obj.get("text", "Tab")) for obj in tab_objects(objects, tabview)]


def tab_of(objects: List[Dict], obj: Dict) -> Optional[Dict]:
    """:return: the tab an object is on (its `parentid` is a tab of the same page), None if it isn't on a tab"""
    if "parentid" not in obj or obj.get("obj") == "tab":
        return None
    return next(
        (
            candidate
            for candidate in objects
            if candidate.get("obj") == "tab"
            and candidate.get("page") == obj.get("page")
            and candidate.get("id") == obj.get("parentid")
        ),
        None,
    )


def last_tabview_id(objects: List[Dict], page: int) -> Optional[int]:
    """:return: the id of the tabview that was added last on a page, None if the page has none"""
    ids = [obj.get("id") for obj in objects if obj.get("obj") == "tabview" and obj.get("page") == page]
    return ids[-1] if ids else None
