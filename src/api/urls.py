from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.routers import SimpleRouter

from api.views import UserViewSet, PaymentViewSet, DemoViewSet,\
    TestViewSet, RequestToPayViewSet, PaymentCallbackViewSet,\
    PaymentLinkViewSet, PaymentCodeView, APIKeyView, ChangePasswordView, \
    TransactionOrangeAPINotifView

router = SimpleRouter()
router.register("user", UserViewSet, basename="user")
router.register("payment", PaymentViewSet, basename="payment")
router.register("requesttopay", RequestToPayViewSet, basename="request_to_pay")
router.register("payment_callback", PaymentCallbackViewSet, basename="payment_callback")
router.register("payment_link", PaymentLinkViewSet, basename="payment_link")

#router.register("demo", DemoViewSet, basename="demo")
#router.register("test", TestViewSet, basename="test")

urlpatterns = [
    path("user/login/", TokenObtainPairView.as_view(), name="obtain_token"),
    path("user/refresh/", TokenRefreshView.as_view(), name="refresh_token"),
    path("user/payment_code/", PaymentCodeView.as_view(), name="payment_code"),
    path("user/apikey/", APIKeyView.as_view(), name="api_key"),
    path("user/change_password/", ChangePasswordView.as_view(), name="change_password"),
    path("external_api/transaction/notif/", TransactionOrangeAPINotifView.as_view(), name="transaction_mobile_money"),
    path("", include(router.urls))
]