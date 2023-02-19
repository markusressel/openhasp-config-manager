def calculate_checksum(content: str) -> str:
    import hashlib
    hash_value = hashlib.md5(content.encode('utf-8')).hexdigest()
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
