# import json
# from core.config import Settings
# from core.kms import decrypt, encrypt
# from core.kms_client import KmsClient
# from core.kms_secret import decrypt_kms_secrets


# def load_config(fname="./data/kms.json"):
#     config = None
#     with open(fname) as f:
#         config = json.load(f)
#     return config


# if __name__ == "__main__":
#     setting = Settings()
#     settting = decrypt_kms_secrets(Settings())
#     print(f"Secret text: {settting.TEST_API_BASE}")
#     # secret_text = "abc"
#     # kms_client = KmsClient()
#     # cipher_text = encrypt(secret_text, kms_client)

#     # config = load_config()
#     # aws_access_key = config["key"]

#     # binary_data = bytes.fromhex(aws_access_key)
#     # text = decrypt(
#     #     binary_data,
#     #     kms_client,
#     # )
#     # print(f"Secret text: {secret_text}")
#     # print(f"cipher_text: {cipher_text}")
#     # print(f"Unencrypted secret text: {text}")
