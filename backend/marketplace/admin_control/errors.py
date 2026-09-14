"""Present validation messages without Python's ErrorDetail representation."""


def error_messages(error):
    if hasattr(error, 'detail'):
        return error_messages(error.detail)
    if hasattr(error, 'messages'):
        return error_messages(error.messages)
    if isinstance(error, dict):
        if 'detail' in error:
            return error_messages(error['detail'])
        return [message for value in error.values() for message in error_messages(value)]
    if isinstance(error, (list, tuple)):
        return [message for value in error for message in error_messages(value)]
    return [str(error)]


def error_text(error):
    return ' '.join(error_messages(error))
