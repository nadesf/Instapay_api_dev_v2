from django.contrib.auth.hashers import check_password
from rest_framework.serializers import ModelSerializer, ValidationError, CharField,\
                    SerializerMethodField, URLField
from api.validators import SerializerValidationMixins
from api.models import UserAccount, PaymentCallback, Transaction, PaymentLink, Provider, Demo, Test


class SignUserCheckerMixinsSerializer(ModelSerializer):

    def validate(self, data):
        if len(data["phone_number"]) != 10:
            raise ValidationError("The size of 'phone_number' is not correct.")
        if len(data["password"]) < 8:
            raise ValidationError("The password must be greater/equal to 8.")
        if UserAccount.objects.filter(phone_number=data["phone_number"]).exists():
            raise ValidationError("This 'phone_number' is already exists.")
        return data
    
class SignupClientSerializer(SignUserCheckerMixinsSerializer, ModelSerializer):

    class Meta:
        model = UserAccount
        fields = ["first_name", "last_name", "phone_number", "password"]
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, data):
        user = UserAccount.objects.create_user(
            phone_number=data["phone_number"],
            password = data["password"]
        )
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]
        user.save()
        return user
    
class SignupMerchantSerializer(SignUserCheckerMixinsSerializer, ModelSerializer):

    class Meta:
        model = UserAccount
        fields = ["first_name", "last_name", "phone_number", "password", "area_activity", "company_name"]
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, data):
        user = UserAccount.objects.create_user(
            phone_number=data["phone_number"],
            password = data["password"]
        )
        user.first_name = data["first_name"]
        user.last_name = data["last_name"]
        user.company_name = data["company_name"]
        user.area_activity = data["area_activity"]
        user.is_merchant = 1
        user.balance = "0"
        user.save()
        return user

class UserSerializer(ModelSerializer):

    class Meta:
        model = UserAccount
        fields = [
            "id", "first_name", "last_name", "phone_number", "double_authentication_status", 
            "transaction_protection_status", "company_name", "area_activity", 
            "balance", "is_merchant"
        ]
        read_only_fields = ['id', "balance", "is_merchant"]
        #extra_kwargs = {"password": {"write_only": True}}

class BaseUserInfoSerializer(ModelSerializer):

    class Meta:
        model = UserAccount
        fields = ["first_name", "last_name", "is_merchant", "company_name"]

class BaseInfoProvider(ModelSerializer):

    class Meta:
        model = Provider
        fields = ["name", "is_active"]

class ProviderSerializer(ModelSerializer):

    class Meta:
        model = Provider
        fields = '__all__'

class DetailPaymentSerializer(ModelSerializer):

    payee = BaseUserInfoSerializer()
    payer = BaseUserInfoSerializer()
    provider = BaseInfoProvider()

    class Meta:
        model = Transaction
        fields = ["id", "payer_address", "amount", "note", "datetime", "status", "payer", "payee", "provider"]

class PaymentSerializer(SerializerValidationMixins, ModelSerializer):

    provider = CharField(max_length=128)
    payee = CharField(max_length=128)

    class Meta:
        model = Transaction
        fields = ["id", "provider", "payer_address", "payee", "amount", "note"]

    def validate(self, data):
        if data["provider"] == "INSTAPAY":
            request = self.context.get("request")
            payer_account = UserAccount.objects.get(phone_number=request.user)
            if int(payer_account.balance) < int(data["amount"]):
                    raise ValidationError({"balance": "This client don't have enough money to perfom this transaction"})
            data["status"] = "SUCCESS"
        elif data["provider"] == "MTN":
            data["payer_address"] = "225"+data["payer_address"]
        return data

class RequestToPaySerializer(SerializerValidationMixins, ModelSerializer):

    provider = CharField(max_length=128)
    code = CharField(max_length=6, write_only=True)

    class Meta:
        model = Transaction
        fields = ["id", "provider", "payer_address", "amount", "note", "code"]
    
    # VERIFICATION DU CODE : LORSQUE LE PAIEMENT EST FAIT DEPUIS LE TERMINAL DU MARCHAND
    def validate_code(self, value):
        if value is None:
            raise ValidationError("The 'code' cannot be null or empty")
        return value

    '''
        Si le marchand reçoit un paiement avec INSTAPAY on s'assure que celui-ci respecte 
        les conditions suivantes : 
        1. Inscrit comme client chez Instapay 
        2. Dispose d'assez de fond pour éffectuer la transaction 
    '''
    
    def validate(self, data):
        if data["provider"] == "INSTAPAY":
            if UserAccount.objects.filter(phone_number=data["payer_address"]).exists:
                payer_account = UserAccount.objects.get(phone_number=data["payer_address"])
                if payer_account.temporary_code != data["code"]:
                    raise ValidationError({"code": "Code to withdraw money from client account is not correct."})
                elif int(payer_account.balance) < int(data["amount"]):
                    raise ValidationError({"balance": "This client don't have enough money to perfom this transaction"})
            else:
                raise ValidationError({"payer_address": "This payer is not Instapay user."})
            data["status"] = "SUCCESS"
        elif data["provider"] == "MTN":
            data["payer_address"] = "225"+data["payer_address"]

        data.pop("code")
        return data

class PaymentCallbackSerializer(ModelSerializer):

    recipient = CharField(max_length=128)

    class Meta:
        model = PaymentCallback
        fields = ["id", "recipient", "amount", "reference", "date_created", "is_active"]

    def validate_recipient(self, value):
        if not UserAccount.objects.filter(phone_number=value).exists():
            raise ValidationError("The 'recipient' of this Paymentcallback has no instapay account.")
        recipient  = UserAccount.objects.get(phone_number=value)
        return recipient
    
    def validate_amount(self, value):
        if int(value) % 5 != 0:
            raise ValidationError("The 'amount' must be a multiple of 5")
        return value

class PaymentLinkSerializer(ModelSerializer):

    payment_link = SerializerMethodField(read_only=True)
    owner = BaseUserInfoSerializer(read_only=True)

    class Meta:
        model = PaymentLink
        fields = ["id","payment_link", "reference", "amount", "date_created", "is_active", "owner"]

    def get_payment_link(self, obj):
        return f"https://localhost:8000/api/v2/{obj.collect_payment_code}"
    
    def validate_amount(self, value):
        if int(value) % 5 != 0:
            raise ValidationError("The 'amount' must be a multiple of 5")
        return value

class PasswordSerializer(ModelSerializer):
    
    old_password = CharField(max_length=128, write_only=True)
    new_password = CharField(max_length=128, write_only=True)

    class Meta:
        model = UserAccount
        fields = ["old_password", "new_password"]

    def validate_new_password(self, value):
        if len(value) < 8:
            raise ValidationError("Password must have more than 8 character.")
        return value

    def validate(self, data):
        request = self.context.get("request")
        user = UserAccount.objects.get(phone_number=request.user)
        if not check_password(data["old_password"], user.password):
            raise ValidationError("The 'old_password' is not correct.")
        return data
        
class ExternalAPITransactionSerializer(ModelSerializer):

    status = CharField(max_length=128, write_only=True)
    notif = CharField(max_length=128, write_only=True)
    txnid = CharField(max_length=128, write_only=True)

    class Meta:
        fields = ["status", "notif", "txnid"]
    
######## DEMO / TEST / DEV  ###########
class ValidationMixins:

    def validate_prix(self, value):
        if int(value) > 100:
            raise ValidationError("Reduce the price")
        return value

    def validate_name(self, value):
        if value == "me":
            raise ValidationError("Good Far")
        return value

    def validate_payer_man(self, value):
        return value

class TestSerializer(ValidationMixins, ModelSerializer):

    username = CharField(max_length=128, write_only=True)

    class Meta:
        model = Test
        fields = ["id", 'name', "number", "demo", "username", "temp"]
        read_only_fields = ["temp"]
    
    def validate_number(self, value):
        if value < 100:
            raise ValidationError("The 'number' must be greater than 10.")
        return value

class DemoSerializer(ValidationMixins, ModelSerializer):

    #demo = TestSerializer(many=True)

    class Meta:
        model = Demo 
        fields = '__all__'
        #validators = [ValidationMixins]

    def create(self, validated_data):
        #validated_data.pop("user")
        demo = Demo.objects.create(**validated_data)
        return demo