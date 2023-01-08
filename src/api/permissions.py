from rest_framework.permissions import BasePermission

class IsMerchant(BasePermission):

    def has_permission(self, request, view):
        try:
            return bool(request.user.is_authenticated and
            request.user.is_merchant)
        except:
            return 0