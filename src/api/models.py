from django.db import models
from django.contrib.auth.hashers import check_password
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from rest_framework_api_key.models import APIKey
import string, random, threading, time

# Create your models here.

class MyUserManager(BaseUserManager):

    def create_user(self, phone_number, password):
        if not phone_number or not password:
            raise ValueError("The parameter 'phone_number' and 'password' are required !")
        
        user = self.model(
            phone_number = self.normalize_phone_number(phone_number) 
        )
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, phone_number, password):
        user = self.create_user(phone_number, password)
        user.is_admin = True 
        user.is_staff = True 
        user.save()
        return user
        
    # Cette méthode permet de supprimer toutes les lettres présentent dans le numéro de téléphone.
    def normalize_phone_number(self, phone_number):
        all_chars = string.ascii_letters
        for letter in all_chars:
            if letter in phone_number:
                phone_number.replace(letter, "")
        return phone_number

class UserAccount(AbstractBaseUser):

    phone_number = models.CharField(unique=True, max_length=10)
    first_name = models.CharField(max_length=100, null=False)
    last_name = models.CharField(max_length=30, null=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    is_merchant = models.BooleanField(default=False)
    temporary_code = models.CharField(max_length=6, null=True)
    double_authentication_status = models.BooleanField(default=False)
    double_authentication_code = models.CharField(max_length=6, null=True)
    transaction_protection_status = models.BooleanField(default=False)
    transaction_protection_code = models.CharField(max_length=4, null=True)
    company_name = models.CharField(max_length=100)
    area_activity = models.CharField(max_length=100)
    balance = models.CharField(max_length=9, default="1000000", null=False)
    data_created = models.DateTimeField(auto_now_add=True)
    api_key = models.CharField(max_length=100)

    USERNAME_FIELD = "phone_number"
    objects = MyUserManager()

    def has_perm(self, perm, obj=None):
        return True 

    def has_module_perms(self, app_label):
        return True

    def double_authentication(self):
        if self.double_authentification_status:
            self.double_authentication_status = False
        else:
            self.double_authentication_status = True
        self.save()
    
    def generate_temporary_code(self):
        numbers = string.digits
        code = ''.join(random.choice(numbers) for i in range(6))
        self.temporary_code = code
        self.save()
        return code

    def disable(self):
        if self.active:
            self.active = False
        self.save()

    def generate_api_key(self, name):
        api_key, key = APIKey.objects.create_key(name=name)
        self.api_key = key
        self.save()
        return key

    def credit(self, amount):
        self.balance = int(self.balance) + int(amount)
        self.save()
    
    def dedit(self, amount):
        self.balance = int(self.balance) - int(amount)
        self.save()

    def cancel_temporary_code(self):
        self.temporary_code = None
        self.save()

class Provider(models.Model):

    name = models.CharField(max_length=20, primary_key=True)
    date_created = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

class Transaction(models.Model):

    id = models.CharField(max_length=255, primary_key=True)
    payer = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name="user_account_payer")
    payer_address = models.CharField(max_length=13)
    payee = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name="user_account_payee")
    amount = models.CharField(max_length=10)
    datetime = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=100)
    status = models.CharField(max_length=128, default="PENDING")
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="provider_payment")
    more_info = models.CharField(max_length=150, default="no more info", null=True)

    def success(self, value):
        if value in "SUCCESS" "PENDING" "FAILED":
            self.status = value
            self.save()
    
    def validate_transaction(self):
        if self.status == "PENDING":
            self.status = "SUCCESS"
            self.save()

    def cancel(self):
        self.status = "FAILED"

    def cancel_transaction(self):
        if self.status == "PENDING":
            self.status = "FAILED"
        self.save()

    def cancel_transaction_countdown(self):
        if self.provider.name == "ORANGE":
            time.sleep(665)
        else:
            time.sleep(365)

        if self.status == "PENDING":
            self.status = "FAILED"
        self.save()

    def countdown(self):
        countdown = threading.Thread(target=self.cancel_transaction_countdown)
        countdown.start()


class PaymentLink(models.Model):

    owner = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name="user_account_owner")
    collect_payment_code = models.CharField(max_length=128)
    reference = models.CharField(max_length=255, unique=True)
    amount = models.CharField(max_length=10, default=0)
    is_active = models.BooleanField(default=True)
    date_created = models.DateTimeField(auto_now_add=True)

    def disable(self):
        if self.is_active:
            self.is_active = False
        self.save()

    def generate_collect_payment_code(self):
        chars = string.digits + string.ascii_letters
        code = ''.join(random.choice(chars) for i in range(20))
        return code

class PaymentCallback(models.Model):

    sender = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name="user_account_sender")
    recipient = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name="user_account_recipient")
    amount = models.CharField(max_length=10)
    reference = models.CharField(max_length=255)
    date_created = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def disable(self):
        if self.is_active:
            self.is_active = False
        self.save()


class RequestInfo(models.Model):

    http_method = models.CharField(max_length=10)
    endpoint = models.CharField(max_length=100)
    user = models.ForeignKey(UserAccount, on_delete=models.CASCADE, related_name="user_account_request")
    ip_address = models.GenericIPAddressField()
    device = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    metadata = models.CharField(max_length=255)
    datetime = models.DateTimeField(auto_now_add=True)

class Demo(models.Model):

    name = models.CharField(max_length=128)
    description = models.CharField(max_length=128)
    prix = models.IntegerField()

class Test(models.Model):

    name = models.CharField(max_length=128, null=True)
    number = models.IntegerField()
    demo = models.ForeignKey(Demo, on_delete=models.CASCADE, related_name="demo")
    temp = models.CharField(max_length=128)

    def remove_temp_code(self):
        time.sleep(20)
        self.temp = "111111"
        self.save()

    def generate_temporary_code(self):
        numbers = string.digits
        code = ''.join(random.choice(numbers) for i in range(6))
        self.temp = code 
        self.save() 
        mythread = threading.Thread(target=self.remove_temp_code)
        mythread.start()