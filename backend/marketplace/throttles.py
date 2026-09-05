from rest_framework.throttling import UserRateThrottle


class MutationThrottle(UserRateThrottle):
    scope = 'sensitive'

    def allow_request(self, request, view):
        if request.method in {'GET', 'HEAD', 'OPTIONS'}:
            return True
        return super().allow_request(request, view)
