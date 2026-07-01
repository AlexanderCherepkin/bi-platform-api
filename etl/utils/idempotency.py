import hashlib


def record_fingerprint(source_system: str, source_id: str, fields: dict) -> str:
    payload = f"{source_system}:{source_id}:{sorted(fields.items())}"
    return hashlib.sha256(payload.encode()).hexdigest()
