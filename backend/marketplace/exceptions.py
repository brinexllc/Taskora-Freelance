from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    original = response.data
    if isinstance(original, dict) and original.get('code') == 'FEE_POLICY_CHANGED':
        # Preserve the machine-readable conflict and fresh preview for new clients.
        response.data = {**original, 'errors': {}}
        return response
    if isinstance(original, dict) and 'detail' in original:
        response.data = {'detail': str(original['detail']), 'errors': {}}
    else:
        def messages(value):
            if isinstance(value, dict):
                return [message for child in value.values() for message in messages(child)]
            if isinstance(value, (list, tuple)):
                return [message for child in value for message in messages(child)]
            return [str(value)]
        response.data = {'detail': ' '.join(messages(original)), 'errors': original}
    return response
