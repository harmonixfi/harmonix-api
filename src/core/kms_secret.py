from typing import Any, Dict, Optional

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_settings import BaseSettings

from core.kms import decrypt
from core.kms_client import KmsClient
from pydantic_core import core_schema
from pydantic.json_schema import JsonSchemaValue


class KMSSecretStr:
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.str_schema()

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        # Update the JSON schema to reflect that this is a secret string
        json_schema = handler(core_schema)
        json_schema.update(type="string", writeOnly=True)
        return json_schema

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value: Any) -> "KMSSecretStr":
        if isinstance(value, cls):
            return value
        return cls(value)

    def __init__(self, value: str):
        self._secret_value = value
        self.decrypted = False

    def __repr__(self) -> str:
        return f"KMSSecretStr('{self}')"

    def __str__(self) -> str:
        return "**********" if self._secret_value else ""

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, KMSSecretStr)
            and self.get_secret_value() == other.get_secret_value()
        )

    def decrypt_secret_value(self, kms_client: KmsClient) -> str:
        if not self.decrypted:
            value = decrypt(self._secret_value, kms_client)
            self._secret_value = value
            self.decrypted = True
        return self._secret_value

    def get_secret_value(self) -> str:
        return self._secret_value


def decrypt_kms_secrets(settings: BaseSettings, kms_client: Optional[KmsClient] = None):
    """
    Decrypts all of the KMSSecretStr values in the settings
    given a KMS key id
    """
    kms_client = kms_client or KmsClient()
    if not kms_client:
        raise ValueError(
            "Either key_id function param or the secrets kms "
            "value must be set in the settings class"
        )

    for k, v in settings.__dict__.items():
        if k == "TEST_API_BASE":
            KMSSecretStr(v).decrypt_secret_value(kms_client)

        if isinstance(v, KMSSecretStr):
            v.decrypt_secret_value(kms_client)

    return settings
