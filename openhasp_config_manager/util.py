from typing import Dict


def calculate_checksum(content: bytes) -> str:
    import hashlib

    hash_value = hashlib.md5(content).hexdigest()
    return hash_value


def merge_dict_recursive(d1: Dict, d2: Dict) -> Dict:
    """
    Merges two dictionaries, preserving even the key/value pairs of nested dictionaries.

    This differs from the built-in "|" operator of python in that the built-in version
    will not preserve a key of a nested dict in d1 if the same dict is present in d2 but
    without the given key.

    :param d1: the first dictionary
    :param d2: the second dictionary
    :return: the merged dictionary
    """
    from copy import deepcopy

    # every value is copied once: the values of d1 that d2 doesn't touch, the values of d2, and nothing twice per nesting level
    result = {}
    for d1_key, d1_value in d1.items():
        if d1_key not in d2:
            result[d1_key] = deepcopy(d1_value)
            continue
        d2_value = d2[d1_key]
        if isinstance(d1_value, dict):
            if not isinstance(d2_value, dict):
                raise AssertionError(f"Incompatible types for merging dict, cannot merge {d1_value} and {d2_value}")
            result[d1_key] = merge_dict_recursive(d1_value, d2_value)
        else:
            result[d1_key] = deepcopy(d2_value)
    for d2_key, d2_value in d2.items():
        if d2_key not in d1:
            result[d2_key] = deepcopy(d2_value)

    return result


def merge_dict_into(target: Dict, source: Dict):
    """
    Like `merge_dict_recursive`, but `target` itself is changed, which saves copying everything in it. The values of `source`
    are copied, so `target` never shares anything with it.
    """
    from copy import deepcopy

    for key, value in source.items():
        if key in target and isinstance(target[key], dict):
            if not isinstance(value, dict):
                raise AssertionError(f"Incompatible types for merging dict, cannot merge {target[key]} and {value}")
            merge_dict_into(target[key], value)
        else:
            target[key] = deepcopy(value)


def add_missing_keys(target: Dict, source: Dict):
    """
    Add what `target` doesn't have from `source` (recursively into dicts), and keep everything it has. The values added are copied.
    """
    from copy import deepcopy

    for key, value in source.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(value, dict):
            if not isinstance(target[key], dict):
                raise AssertionError(f"Incompatible types for merging dict, cannot merge {value} and {target[key]}")
            add_missing_keys(target[key], value)


def merge_dict_shared(d1: Dict, d2: Dict) -> Dict:
    """
    Like `merge_dict_recursive`, but the values are shared with `d1` and `d2` instead of copied (only the dicts that are merged
    are new). For results that are only read, or copied before they are changed.
    """
    result = dict(d1)
    for key, value in d2.items():
        if isinstance(result.get(key), dict):
            if not isinstance(value, dict):
                raise AssertionError(f"Incompatible types for merging dict, cannot merge {result[key]} and {value}")
            result[key] = merge_dict_shared(result[key], value)
        else:
            result[key] = value
    return result
