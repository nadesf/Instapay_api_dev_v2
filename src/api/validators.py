from api.models import UserAccount, Provider
from rest_framework.validators import ValidationError

# Contrôle de validité sur les champs.
class SerializerValidationMixins:

    def validate_amount(self, value):
        if int(value) % 5 != 0:
            raise ValidationError("The 'amount' must be a multiple of 5")
        return value

    def validate_note(self, value):
        if value is False:
            value = "Paiement avec Instapay"
        return value

    def validate_provider(self, value):
        if not Provider.objects.filter(name=value).exists():
            raise ValidationError(f" Provider '{value}' is not supported.")
        return value

    def validate_payee(self, value):
        if not UserAccount.objects.filter(phone_number=value).exists(): # Si l'utilisateur existe pas
            raise ValidationError("The 'payee' of the transaction does nos exists.")
        return value