import uuid, requests, json, datetime, time, threading

class MTNMoneyAPI:
    def __init__(self):

        # Les accès
        self.apiUser = "b3045c0f-67ae-4d99-9ee1-48f75e82eb44"
        self.apiKey = "b8fc9d0d5e024122b9f00027e746bf52"
        self.subcriptionKey = "7c2b8a7edafe4b36858020ae20932ec2"
        self.environnement = "mtnivorycoast"

        self.hostMomoAPI = "https://ericssonbasicapi1.azure-api.net"
        self.loginURL = self.hostMomoAPI + "/collection/token/"
        self.requestToPayURL = self.hostMomoAPI + "/collection/v1_0/requesttopay"
        self.accountBalanceURL = self.hostMomoAPI + "/collection/v1_0/account/balance"
        self.callbackURL = ""

        self.loginState = 0

    def login(self):
        headers = {
            "Ocp-Apim-Subscription-Key": self.subcriptionKey
        }
        if not self.loginState:
            req = requests.post(self.loginURL, headers=headers, auth=(self.apiUser, self.apiKey))
            #print("[+] Authentication ")
            #print(req.json())
            if req.status_code != 200:
                return 0
            self.accessToken = req.json()["access_token"]
            self.expireIn = req.json()["expires_in"]  
            self.loginState = 1

        return 1

    def requestToPay(self, payer, amount, transactionId, note):
        self.referenceId = str(uuid.uuid4())
        headers = {
            "Authorization": "Bearer " + self.accessToken,
            "X-Callback-Uri": "https://164.92.134.116/api/v1/external_api/transaction/notif/",
            "X-Reference-Id": self.referenceId,
            "X-Target-Environment": self.environnement,
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": self.subcriptionKey,
        }
        body = {
            "amount": amount,
            "currency": "XOF",
            "externalId": transactionId,
            "payer": {
                "partyIdType": "MSISDN",
                "partyId": payer,
            },
            "payerMessage": note,
            "payeeNote": note
        }
        req = requests.post(url=self.requestToPayURL, headers=headers, data=json.dumps(body))
        if req.status_code != 202:
            return 0
        #print(req)
        return 1, self.referenceId

    def transactionState(self, id):
        headers = {
            "Authorization": "Bearer " + self.accessToken,
            "X-Target-Environment": self.environnement,
            "Ocp-Apim-Subscription-Key": self.subcriptionKey,
        }

        for i in range(6):
            req = requests.get(url=self.requestToPayURL+"/"+id, headers=headers)
            if req.status_code != 200:
                #return (0, "Impossible to get status of this transaction")
                #return (1, req.json()["status"])
                print(req.json()["status"])
                time.sleep(60)
                print(f"============={str(i+1)}================")
            else:
                print(req.json())
                time.sleep(60)
                print(f"============={str(i+1)}================")

    def accountBalance(self):
        headers = {
            "Authorization": "Bearer " + self.accessToken,
            "X-Target-Environnement": self.environnement,
            "Ocp-Apim-Subscription-Key": self.subcriptionKey,
        }
        req = requests.get(url=self.accountBalanceURL, headers=headers)

        if req.status_code == 200:
            return (1, req.json())
        elif req.status_code == 400:
            return (0, "Problem with Reference-Id paramter")
        elif req.status_code == 500:
            return (0, "Problem with mtn server")

    def collect_payment(self, payer, amount, transactionId, note):
        login = self.login()
        print(f"login {login}")
        if login:
            req = self.requestToPay(payer, amount, transactionId, note)
            if not req:
                return (0, "transaction failed")
            return req
        else:
            return (0, "login failed")

class OrangeMoneyAPI:

    def __init__(self):
        
        self.authorization = "Basic a0piaEpUd2JHQnJqM2dZVTVJYTZiZVZlQmRvZ1ZQT2E6QlZTOHY4UENydmJqSFdFUA=="

        self.loginURL = "https://api.orange.com/oauth/v3/token"
        self.requestToPayURL = "https://api.orange.com/orange-money-webpay/ci/v1/webpayment"
        self.transactionStatusURL = "https://api.orange.com/orange-money-webpay/ci/v1/transactionstatus"

    def login(self):
        body = "grant_type=client_credentials"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": self.authorization
        }
        req = requests.post(self.loginURL, data=body, headers=headers)

        if req.status_code == 200:
            self.access_token = req.json()["access_token"]
            return 1
        return 0

    def requesttopay(self, transaction_id, amount, note):

        self.amount = amount
        self.transactionId = transaction_id
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.access_token,
        }
        body = {
            "merchant_key": "2d2e218c",
            "currency": "XOF",
            "order_id": self.transactionId,
            "amount": int(self.amount),
            "return_url": "http://159.223.7.139/payment/success/",
            "cancel_url": "http://159.223.7.139/payment/failed/",
            "notif_url": "https://164.92.134.116/api/v1/external_api/transaction/notif/",
            "lang": "fr",
            "reference": note
        }
        req = requests.post(self.requestToPayURL, data=json.dumps(body), headers=headers)
        #print(req.json())
        #self.pay_token = req.json()["pay_token"]
        #self.notif_token = req.json()["notif_token"]
        #return 1, self.pay_token, self.notif_token
        return req

    def getTransactionStatus(self):

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.access_token,
        }
        body = {
            "order_id": self.transactionId,
            "amount": int(self.amount),
            "pay_token": self.pay_token,
        }
        req = requests.post(self.transactionStatusURL, data=json.dumps(body), headers=headers)

    def collect_payment(self, transaction_id, amount, note):
        login = self.login()
        if login:
            success, pay_token, notif_token = self.requesttopay(transaction_id, amount, note)
            if not success:
                return (0, "Transaction failed")
            return 1, pay_token, notif_token
        else:
            return (0, "Impossible to login to Orange Money API")



#mtn_money = MTNMoneyAPI()
#result = mtn_money.collect_payment("2250554061074", "TIDJBJSBjbvhsdJDSG", "100", "Test Instapay")
#print(result)
mtn_money = MTNMoneyAPI()
if mtn_money.login():
    success, id = mtn_money.requestToPay("2250502455611", "100", "TIDBFIpxushqEZNUHy", "Paiment Instapay")
    print(success)
    print(id)
    mythread = threading.Thread(target=mtn_money.transactionState, args=(id,))
    mythread.start()

mtn_money_2 = MTNMoneyAPI()
if mtn_money_2.login():
    success, id = mtn_money_2.requestToPay("2250502455611", "100", "TIDBFIZxsjxNUHy", "Paiment Instapay")
    print(success)
    print(id)
    #mythread2 = threading.Thread(target=mtn_money_2.transactionState, args=(id,))
    #mythread2.start()

"""

OrangeMoney = OrangeMoneyAPI()
#success, msg = OrangeMoney.collect_payment("TIDMANUIHHD01", "100", "demo")
#print(success)
#print(msg)
if OrangeMoney.login():
    req = OrangeMoney.requesttopay("TIDJZXZBsjns5E", "1000", "demo")
    print(req.json())


if OrangeMoney.login():
    transactionId = "TIDMANUIHHD"
    amount = 100
    result = OrangeMoney.requesttopay(transactionId, amount, "Test InstaPay")
    print(result)

for i in range(12):
    print(f"========= {str(i+1)} ==========")
    req = OrangeMoney.getTransactionStatus()
    print(req)
    time.sleep(60)

MTNMoney = MomoAPI()
MTNMoney.login()

#payer = "2250502455611"
#MTNMoney.accountBalance()

#eyJ0eXAiOiJKV1QiLCJhbGciOiJSMjU2In0.eyJjbGllbnRJZCI6ImIzMDQ1YzBmLTY3YWUtNGQ5OS05ZWUxLTQ4Zjc1ZTgyZWI0NCIsImV4cGlyZXMiOiIyMDIyLTEyLTEzVDAxOjAxOjA3LjEyMyIsInNlc3Npb25JZCI6IjljZWM4OWI5LTdiZDQtNDgzOS1iOTY1LTAxNjdmM2UwMWM0MCJ9.QFQI8QfxuUpojIYv8xaDp6GQcQlpofKF8csrmkzDQj1v1OIYwqmfgqFEWmfK-rcUl3t-RPrkvQaXQqAy6jAtR7ApYF_Yy2hDzzUFCLwU_6yD3cWZ1RJrC-ZpkNES03GMs-x-8m4ti3m8597V4G8IBMDS-smjTwMV_XDdMDrEb_hj2XGyQxFzq8V8FA_dePTWoWCZrVvvEJsAt_bp5CKq63ecKJ41p4qXbj1K4viGkaTuGSrLKQgpKyUOZfU4MajVsifnV02gTm1X27wb6qip1BCp1k7M71ligzwMhmmzpJdnvcxwy7TVQwR7C-A6n476j_TntDHb7VatsPy0bu-_iQ

#payer = "2250565101231"
payer_axel = "2250554061074"
payer_labtic = "2250554899932"
payer_junior = "2250596201827"
transactionId = generate_transaction_id()
amount = "50"
referenceIdTransaction = str(uuid.uuid4())
result = MTNMoney.requestToPay(payer_junior, amount, transactionId, referenceIdTransaction)
for i in range(6):
    success, result = MTNMoney.transactionState(referenceIdTransaction)
    if success:
        print(result["status"])
    else:
        print(result)
        break
    print(f"================= {str(i+1)} Min ====================")
    time.sleep(60)

print(result)
"""