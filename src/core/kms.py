import base64
from pydantic_settings import BaseSettings
import boto3
from typing import Any, Dict

from core.kms_client import KmsClient

ENCRYPTION_ALGORITHM = "RSAES_OAEP_SHA_1"


def encrypt(secret_text, kms_client: KmsClient) -> str:
    """
    Use asymmetric encryption with the Aws Kms Sdk in Python to encrypt a string with a given Kms Key Id (ARN).
    :param s:
    :return cipher_text:
    """
    cipher_text = kms_client.create_kms_client().encrypt(
        KeyId=kms_client.aws_kms_arn,
        Plaintext=secret_text.encode(),
        EncryptionAlgorithm=ENCRYPTION_ALGORITHM,
    )["CiphertextBlob"]
    return cipher_text


def decrypt(cipher_text, kms_client: KmsClient) -> str:
    """
    Takes a KMS key id, decrypts the value using it and
    returns the decrypted value
    """
    text = kms_client.create_kms_client().decrypt(
        KeyId=kms_client.aws_kms_arn,
        CiphertextBlob=cipher_text,
        EncryptionAlgorithm=ENCRYPTION_ALGORITHM,
    )["Plaintext"]
    return text.decode()
