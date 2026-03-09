from uuid import UUID


def force_uuid(id: object) -> UUID:
    if isinstance(id, str):
        return UUID(id)
    elif isinstance(id, UUID):
        return id
    else:
        raise ValueError(f"Invalid UUID: {id}")
