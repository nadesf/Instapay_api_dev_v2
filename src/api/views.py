#from django.shortcuts import render
from django.shortcuts import get_list_or_404, get_object_or_404
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, CreateModelMixin
from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework_api_key.permissions import HasAPIKey
from rest_framework.decorators import action
from rest_framework.response import Response

from api.serializers import UserSerializer, SignupClientSerializer, \
        SignupMerchantSerializer, PaymentSerializer, DemoSerializer, \
        DetailPaymentSerializer, RequestToPaySerializer, TestSerializer, \
        PaymentCallbackSerializer, PaymentLinkSerializer, PasswordSerializer, \
        ExternalAPITransactionSerializer

from api.models import UserAccount, Transaction, Provider, Demo, Test, \
    PaymentCallback, PaymentLink

from api.permissions import IsMerchant
from external_api.mobile_money import MTNMoneyAPI, OrangeMoneyAPI
import string, random, threading, time

# Create your views here.

def check_transaction_status_mtn(momo_instance, reference_id):
    time.sleep(2)
    transaction = Transaction.objects.get(more_info=reference_id)
    for i in range(24):
        success, status = momo_instance.transactionState(reference_id)
        if status == "SUCCESS" and transaction.status == "PENDING":
            payee_account = UserAccount.objects.get(pk=transaction.payee)
            payee_account.credit(transaction.amount)
            transaction.validate_transaction()
            break
        elif status == "FAILED" and transaction.status == "PENDING":
            transaction.cancel_transaction()
            break
        time.sleep(15)
    transaction.cancel_transaction()

def check_transaction_status_orange(orange_instance, notif_token):
    time.sleep(2)
    transaction = Transaction.objects.get(more_info=notif_token)
    for i in range(44):
        result = orange_instance.getTransactionStatus()
        if result["status"] == "SUCCESS" and transaction.status == "PENDING":
            payee_account = UserAccount.objects.get(pk=transaction.payee)
            payee_account.credit(transaction.amount)
            transaction.validate_transaction()
            break
        elif result["status"] == "FAILED" and transaction.status == "PENDING":
            transaction.cancel_transaction()
            break
        time.sleep(15)
    transaction.cancel_transaction()

# vCI1d3NY.SYORNToAFl7OrfwCWnhspR96KthiNJdh

class UserViewSet(ModelViewSet):

    serializer_class = UserSerializer

    def get_queryset(self):
        queryset = get_list_or_404(UserAccount, phone_number=self.request.user, is_active=True)
        return queryset

    def partial_update(self, request, *args, **kwargs):
        queryset = get_object_or_404(UserAccount, phone_number=self.request.user, is_active=True)
        serializer = UserSerializer(queryset, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def get_serializer_class(self):
        if self.action == "create":
            if self.request.GET.get("as_merchant"):
                return SignupMerchantSerializer
            else:
                return SignupClientSerializer
        elif self.action != "create":
            return super().get_serializer_class()

    def get_permissions(self):
        if self.action == "create":
            self.permission_classes = [HasAPIKey]
        else:
            self.permission_classes = [IsAuthenticated]

        return super().get_permissions()

'''
                        LES PAIEMENTS
    Nous gérons ici, les paiements initié à partir d'un terminal client / marchand.
    Le client / marchand doit avoir une authorisation (token uniquement) afin réaliser cette 
    opération.
'''
class PaymentViewSet(ListModelMixin,
                  RetrieveModelMixin,
                  CreateModelMixin, 
                  GenericViewSet):

    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer
    detail_serializer_class = DetailPaymentSerializer

    def get_queryset(self):
        type = self.request.GET.get("type")
        user = UserAccount.objects.get(phone_number=self.request.user)
        if type == "payer":
            queryset = Transaction.objects.filter(payer=user.id)
        else:
            queryset = Transaction.objects.filter(payee=user.id)
        return queryset

    def create(self, request, *args, **kwargs):
        request.data["id"] = self.generate_transaction_id()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # AJOUT DES DONNEES SUPPLEMENTAIRE POUR L'ENREGISTREMENT.
        serializer.validated_data["provider"] = Provider.objects.get(name=request.data["provider"])
        serializer.validated_data["payee"] = UserAccount.objects.get(phone_number=request.data["payee"])
        serializer.validated_data["payer"] = UserAccount.objects.get(phone_number=self.request.user)
        
        provider = serializer.validated_data["provider"]
        payee = serializer.validated_data["payee"]
        payer = serializer.validated_data["payer"]

        # EXECUTIONS DE LA TRANSACTION
        if provider.name == "INSTAPAY":
            payer.balance = int(payer.balance) - int(serializer.validated_data.get('amount'))
            payee.balance = int(payee.balance) + int(serializer.validated_data.get('amount'))
            payer.save()
            payee.save()
            serializer.validated_data["status"], request.data["status"] = "SUCCESS", "SUCCESS" #On valide la transaction
            
        elif provider.name == "MTN":
            MomoAPI = MTNMoneyAPI()
            success, reference_id = MomoAPI.collect_payment(serializer.validated_data["payer_address"], request.data["amount"], request.data["id"], serializer.validated_data["note"])
            if not success:
                return Response({"Internal_error": "Impossible to pay with MTN for the moment, please try later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            check_mtn_transaction_status = threading.Thread(target=check_transaction_status_mtn, args=(MomoAPI, reference_id))
            check_mtn_transaction_status.start()
            request.data["status"] = "PENDING"
            serializer.validated_data["more_info"] = reference_id

        elif provider.name == "ORANGE":
            OrangeMoney = OrangeMoneyAPI()
            success, payment_url, notif_token = OrangeMoney.collect_payment(request.data["id"], request.data["amount"], request.data["note"])
            if not success:
                return Response({"Internal_error": "Impossible to pay with ORANGE for the moment, please try later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            check_orange_transaction_status = threading.Thread(target=check_transaction_status_orange, args=(OrangeMoney, notif_token))
            check_orange_transaction_status.start()
            request.data["status"] = "PENDING"
            request.data["link_to_pay"] = payment_url
            serializer.validated_data["more_info"] = notif_token

        # ENREGISTREMENT DE LA TRANSACTION
        serializer.save()
        headers = self.get_success_headers(request.data)
        return Response(request.data, status=status.HTTP_201_CREATED, headers=headers)
    
    def get_serializer_class(self):
        if self.action == "list" or self.action == "retrieve":
            return DetailPaymentSerializer
        else:
            return PaymentSerializer
    
    def generate_transaction_id(self):
        chars = string.ascii_uppercase + string.digits
        transaction_id = "TID"
        for i in range(7):
            transaction_id = transaction_id + random.choice(chars)
        return transaction_id

'''
                    LES REQUETES DE PAIEMENT
    Nous gérons ici, les requêtes de paiement initié à partir d'un terminal marchand
    ou d'un développeur tiers. Le Marchand / Développeur devra avoir soit un token 
    d'authentification ou une APIKey afin de réaliser cette opération.
'''
class RequestToPayViewSet(ListModelMixin,
                  RetrieveModelMixin,
                  CreateModelMixin, 
                  GenericViewSet):
    
    permission_classes = [IsMerchant | HasAPIKey ]
    serializer_class = RequestToPaySerializer
    detail_srializer_class = DetailPaymentSerializer

    def get_queryset(self):
        # IDENTIFIONS LE MARCHAND DE LA TRANSACTION 
        authorization = self.request.headers['Authorization']
        if "Api-Key" in authorization:
            api_key = authorization.replace("Api-Key ", "")
            payee = UserAccount.objects.get(api_key=api_key)
        else:
            payee = UserAccount.objects.get(phone_number=self.request.user)
        
        type = self.request.GET.get("type")
        if type == "payee":
            queryset = Transaction.objects.get(payer=self.request.user)
        else:
            queryset = Transaction.objects.get(payee=self.request.user)
        return queryset

    def create(self, request, *args, **kwargs):
        request.data["id"] = self.generate_transaction_id()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # IDENTIFIONS LE MARCHAND DE LA TRANSACTION 
        authorization = self.request.headers['Authorization']
        if "Api-Key" in authorization:
            api_key = authorization.replace("Api-Key ", "")
            payee = UserAccount.objects.get(api_key=api_key)
        else:
            payee = UserAccount.objects.get(phone_number=self.request.user)

        # AJOUT DES DONNEES SUPPLEMENTAIRE POUR L'ENREGISTREMENT.
        serializer.validated_data["provider"] = Provider.objects.get(name=request.data["provider"])
        serializer.validated_data["payee"] = payee
        provider = serializer.validated_data["provider"]

        # EXECUTIONS DE LA TRANSACTION
        if provider.name == "INSTAPAY":
            serializer.validated_data["payer"] = UserAccount.objects.get(phone_number=request.data["payer_address"])
            payer = serializer.validated_data["payer"]
            payer.balance = int(payer.balance) - int(serializer.validated_data.get('amount'))
            payee.balance = int(payee.balance) + int(serializer.validated_data.get('amount'))
            payer.temporary_code = None
            payer.save()
            payee.save()
            serializer.validated_data["status"], request.data["status"] = "SUCCESS", "SUCCESS" #On valide la transaction
            
        elif provider.name == "MTN":
            MomoAPI = MTNMoneyAPI()
            success, reference_id = MomoAPI.collect_payment(serializer.validated_data["payer_address"], request.data["amount"], request.data["id"], serializer.validated_data["note"])
            if not success:
                return Response({"Internal_error": "Impossible to pay with MTN for the moment, please try later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            check_mtn_transaction_status_for_req_to_pay = threading.Thread(target=check_transaction_status_mtn, args=(MomoAPI, reference_id))
            check_mtn_transaction_status_for_req_to_pay.start()
            request.data["status"] = "PENDING"
            serializer.validated_data["payer"] = UserAccount.objects.get(phone_number="0000000000")

        elif provider.name == "ORANGE":
            OrangeMoney = OrangeMoneyAPI()
            success, payment_url, notif_token = OrangeMoney.collect_payment(request.data["id"], request.data["amount"], request.data["note"])
            if not success:
                return Response({"Internal_error": "Impossible to pay with ORANGE for the moment, please try later."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            check_orange_transaction_status_for_req_to_pay = threading.Thread(target=check_transaction_status_orange, args=(OrangeMoney, notif_token))
            check_orange_transaction_status_for_req_to_pay.start()
            request.data["status"] = "PENDING"
            request.data["link_to_pay"] = payment_url
            serializer.validated_data["more_info"] = notif_token
            serializer.validated_data["payer"] = UserAccount.objects.get(phone_number="0000000000")

        # ENREGISTREMENT DE LA TRANSACTION
        serializer.save()
        headers = self.get_success_headers(request.data)
        return Response(request.data, status=status.HTTP_201_CREATED, headers=headers)

    def get_serializer_class(self):
        if self.action == "list" or self.action == "retrieve":
            return DetailPaymentSerializer
        else:
            return RequestToPaySerializer

    def generate_transaction_id(self):
        chars = string.ascii_uppercase + string.digits
        transaction_id = "TID"
        for i in range(7):
            transaction_id = transaction_id + random.choice(chars)
        return transaction_id

'''
                    LES CODES DE PAIEMENT TEMPORAIRE 
    Cette section gère la création des codes à chiffres qui permettrons à un marchand
    de retirer l'argent du compte d'un client afin de satisfaire un paiement
'''
class PaymentCodeView(views.APIView):
    
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = UserAccount.objects.get(phone_number=request.user)
        return Response({"payment_code": queryset.temporary_code})

    def post(self, request):
        queryset = UserAccount.objects.get(phone_number=request.user)
        code = queryset.generate_temporary_code()
        return Response({"payment_code": code, "expires_in": "5min"})

'''
                                API-KEY
    On traite ici les requêtes de paiement qui arrive avec les Api-Keys
    Uniquement pour les développeurs qui souhaite utiliser notre API comme moyen de
    collecte de paiement.
'''
class APIKeyView(views.APIView):

    permission_classes = [IsMerchant]
    
    def get(self, request):
        queryset = UserAccount.objects.get(phone_number=request.user)
        return Response({"api_key": queryset.apikey})

'''
                PASSWORD CHANGE
    Changement de mot de passe d'un utilisateur.
'''
class ChangePasswordView(views.APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = UserAccount.objects.get(phone_number=request.user)
        #serializer = PasswordSerializer(data=request.data)
        #serializer.is_valid(raise_exception=True)
        #user.set_password(serializer.validated_data["new_password"])
        user.set_password(request.data['new_password'])
        return Response({"password": "Password updated."})     

'''
                            Rappel de paiement
    Les rappels de paiement sont des messages qu'un marchand envoie à un client
    afin que celui ci, remplisse une obligation de paiement. Seul les marchands
    authentifiés avec un token ont accès à cette fonctionnalité
'''

class PaymentCallbackViewSet(ModelViewSet):

    permission_classes = [IsAuthenticated]
    serializer_class = PaymentCallbackSerializer

    def get_queryset(self):
        #self.request.user = "0000000000"
        user = UserAccount.objects.get(phone_number=self.request.user)
        queryset = PaymentCallback.objects.filter(sender=user)
        return queryset

    def perform_create(self, serializer):
        #self.request.user = "0000000000"
        serializer.validated_data["sender"] = UserAccount.objects.get(phone_number=self.request.user)
        return super().perform_create(serializer)

'''
                            Lien de paiement
    Les liens de paiements sont des URLs appartenant à un marchand et qui lui
    permettent de recevoir des paiements de ces clients.
'''
class PaymentLinkViewSet(ModelViewSet):

    permission_classes = [IsMerchant]
    serializer_class = PaymentLinkSerializer

    def get_queryset(self):
        user = UserAccount.objects.get(phone_number=self.request.user)
        queryset = PaymentLink.objects.filter(owner=user)
        return queryset

    def perform_create(self, serializer):
        serializer.validated_data["owner"] = UserAccount.objects.get(phone_number=self.request.user)
        serializer.validated_data["collect_payment_code"] = PaymentLink.generate_collect_payment_code(self)
        return super().perform_create(serializer)

'''
                    TRANSACTION NOTIFICATION 
    Cette section est pour le retour des API externe de paiement concernant
    les paiements de nos clients. Lorsque le paiement validé alors on débite
    le compte INSTAPAY du bénéficiaire de la transaction 
'''
class TransactionOrangeAPINotifView(views.APIView):
    
    def post(self, request):
        try:
            serializer = ExternalAPITransactionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            transaction = Transaction.objects.get(more_info=request.data["notif_token"])
            if request.data["status"] == "SUCCESS" and transaction.status == "PENDING":
                payee_account = UserAccount.objects.get(pk=transaction.payee)
                payee_account.credit(transaction.amount)
                transaction.validate_transaction()
            else:
                transaction.cancel_transaction()
        except:
            pass
        return Response({"notif": "transaction notif received."})

######### DEMO / TEST / DEV ##########

class DemoViewSet(ListModelMixin,
                  RetrieveModelMixin,
                  CreateModelMixin, 
                  GenericViewSet):

    serializer_class = DemoSerializer

    def get_queryset(self):
        queryset = Demo.objects.all()
        return queryset  
    
    @action(detail=False, methods=["post"])
    def write_some_thing(self):
        with open("betatest.txt", "a") as fic:
            fic.write("We catch something !")

class TestViewSet(ModelViewSet):

    #permission_classes = [HasAPIKey]
    serializer_class = TestSerializer
    
    def get_queryset(self):
        queryset = Test.objects.all()
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("username")
        serializer.save()
        Test.objects.get(name=serializer.validated_data.get("name")).generate_temporary_code()
        return Response(request.data, status=status.HTTP_201_CREATED)