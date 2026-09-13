"""Maintenance pauses new participant writes while keeping access and settlement callbacks."""
from django.http import JsonResponse


class MaintenanceMiddleware:
    ALLOWED = (
        '/api/payments/click/', '/api/payments/payme/', '/api/admin/',
        '/api/auth/login/', '/api/auth/logout/', '/api/auth/csrf/',
        '/api/auth/mfa/', '/api/auth/confirm-sensitive/', '/api/auth/change-password/',
        '/api/auth/sessions/', '/api/auth/password-reset/', '/api/auth/consent/',
        '/api/support/', '/api/disputes/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.path.startswith('/api/') and not request.path.startswith(self.ALLOWED):
            from ..security import is_platform_admin
            if not is_platform_admin(request.user):
                from .content_services import get_setting
                if get_setting('maintenance_enabled', False):
                    response = JsonResponse({'code': 'maintenance', 'detail': 'Плановое обслуживание. Новые операции временно недоступны; история и поддержка доступны.'}, status=503)
                    response['Retry-After'] = '300'
                    response['Cache-Control'] = 'no-store'
                    return response
        return self.get_response(request)
