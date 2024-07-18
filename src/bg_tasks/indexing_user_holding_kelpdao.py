from web3 import Web3
from core.abi_reader import read_abi
from core.config import settings


w3 = Web3(Web3.HTTPProvider(settings.ARBITRUM_MAINNET_INFURA_URL))

rockonyx_delta_neutral_vault_abi = read_abi("rockonyxrestakingdeltaneutralvault")
vault_contract = w3.eth.contract(
    address="0x4a10C31b642866d3A3Df2268cEcD2c5B14600523",
    abi=rockonyx_delta_neutral_vault_abi,
)


balance = vault_contract.functions.balanceOf(
    Web3.to_checksum_address("0x502082ebf1541bdb4817fcb15a544ebbe556b058")
).call(block_identifier=233108297)
print(balance)
