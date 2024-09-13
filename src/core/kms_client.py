import json
import boto3
from pydantic_settings import BaseSettings


class KmsClient:
    def __init__(
        self,
    ):
        self.config = self.load_config()
        self.aws_access_key = self.config["aws_access_key"]
        self.aws_secret_access_key = self.config["aws_secret_access_key"]
        self.aws_kms_arn = self.config["aws_kms_arn"]
        self.aws_region_name = self.config["aws_region_name"]
        self.kms_client = self.create_kms_client()

    def create_kms_client(self):
        return boto3.client(
            "kms",
            region_name=self.aws_region_name,
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_access_key,
        )

    def return_kms_client(self):
        return self.kms_client

    def load_config(self, fname="./data/kms.json"):
        config = None
        with open(fname) as f:
            config = json.load(f)
        return config
