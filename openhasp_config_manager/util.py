def calculate_checksum(content: str) -> str:
    import hashlib
    hash_value = hashlib.md5(content.encode('utf-8')).hexdigest()
    return hash_value
