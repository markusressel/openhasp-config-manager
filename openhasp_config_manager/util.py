from typing import Dict


def calculate_checksum(content: bytes) -> str:
    import hashlib
    hash_value = hashlib.md5(content).hexdigest()
    return hash_value


def contains_nested_dict_key(d: dict, key: str) -> bool:
    """
    Recursively checks if any key in a nested dictionary structure is equal to the given string.
    :param d: the dictionary to check
    :param key: the key to search for
    :return: True if the string is found in any key, False otherwise
    """
    stack = [d]
    while stack:
        curr = stack.pop()
        for k, v in curr.items():
            if k == key:
                return True
            if isinstance(v, dict):
                stack.append(v)
    return False


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

    result = deepcopy(d1)
    for d2_key, d2_value in d2.items():
        if d2_key in d1:
            d1_value = d1[d2_key]
            if isinstance(d1_value, dict):
                if not isinstance(d2_value, dict):
                    raise AssertionError(f"Incompatible types for merging dict, cannot merge {d1_value} and {d2_value}")

                result[d2_key] = merge_dict_recursive(d1_value, d2_value)
            else:
                result[d2_key] = deepcopy(d2_value)
        else:
            result[d2_key] = deepcopy(d2_value)

    return result
