#!/usr/bin/env python
import asyncio
from typing import Optional

import aiohttp
import click
import requests
from blspy import PrivateKey, AugSchemeMPL

from chia.cmds.wallet_funcs import get_wallet
from chia.consensus.default_constants import DEFAULT_CONSTANTS
from chia.rpc.wallet_rpc_client import WalletRpcClient
from chia.types.blockchain_format.coin import Coin
from chia.types.spend_bundle import SpendBundle
from chia.util.config import load_config
from chia.util.default_root import DEFAULT_ROOT_PATH
from chia.util.ints import uint16, uint32
from chia.wallet.derive_keys import master_sk_to_singleton_owner_sk
from chia.wallet.puzzles import p2_delegated_puzzle_or_hidden_puzzle
from chia.wallet.puzzles.singleton_top_layer import SINGLETON_LAUNCHER_HASH
from chia.wallet.transaction_record import TransactionRecord
from ownable_singleton.drivers.ownable_singleton_driver import (
    SINGLETON_AMOUNT,
    create_unsigned_ownable_singleton,
)

SINGLETON_GALLERY_API = "https://xch.gallery/api"
SINGLETON_GALLERY_FRONTEND = "https://xch.gallery"


# Loading the client requires the standard chia root directory configuration that all of the chia commands rely on
async def get_client() -> Optional[WalletRpcClient]:
    config = load_config(DEFAULT_ROOT_PATH, "config.yaml")
    self_hostname = config["self_hostname"]
    wallet_rpc_port = config["wallet"]["rpc_port"]

    try:
        wallet_client = await WalletRpcClient.create(
            self_hostname, uint16(wallet_rpc_port), DEFAULT_ROOT_PATH, config
        )
        return wallet_client
    except Exception as e:
        if isinstance(e, aiohttp.ClientConnectorError):
            print(f"Connection error. Check if wallet is running at {wallet_rpc_port}")
        else:
            print(f"Exception from 'wallets' {e}")
        return None


async def create_genesis_coin(fingerprint, amt, fee) -> [TransactionRecord, PrivateKey]:
    try:
        wallet_client: WalletRpcClient = await get_client()
        wallet_client_f, fingerprint = await get_wallet(wallet_client, fingerprint)

        private_key = await wallet_client.get_private_key(fingerprint)
        master_sk = PrivateKey.from_bytes(bytes.fromhex(private_key["sk"]))
        singleton_sk = master_sk_to_singleton_owner_sk(master_sk, uint32(0))

        singleton_wallet_puzhash = p2_delegated_puzzle_or_hidden_puzzle.puzzle_for_pk(
            singleton_sk.get_g1()
        ).get_tree_hash()

        signed_tx = await wallet_client.create_signed_transaction(
            [{"puzzle_hash": singleton_wallet_puzhash, "amount": amt}], fee=fee
        )
        return signed_tx, singleton_sk
    finally:
        wallet_client.close()
        await wallet_client.await_closed()


@click.group()
def cli():
    pass


@cli.command()
@click.option("--name", prompt=True, help="The name of the NFT")
@click.option("--uri", prompt=True, help="The uri of the main NFT image")
@click.option("--fingerprint", type=int, help="The fingerprint of the key to use")
@click.option(
    "--fee",
    required=True,
    default=0,
    show_default=True,
    help="The XCH fee to use for this transaction",
)
def create(name: str, uri: str, fingerprint: int, fee: int):
    signed_tx: TransactionRecord
    owner_sk: PrivateKey
    signed_tx, owner_sk = asyncio.get_event_loop().run_until_complete(
        create_genesis_coin(fingerprint, SINGLETON_AMOUNT, fee)
    )
    genesis_coin: Coin = next(
        coin for coin in signed_tx.additions if coin.amount == SINGLETON_AMOUNT
    )
    genesis_puzzle = p2_delegated_puzzle_or_hidden_puzzle.puzzle_for_pk(
        owner_sk.get_g1()
    )

    coin_spends, delegated_puzzle = create_unsigned_ownable_singleton(
        genesis_coin, genesis_puzzle, owner_sk.get_g1(), uri, name
    )

    synthetic_secret_key: PrivateKey = (
        p2_delegated_puzzle_or_hidden_puzzle.calculate_synthetic_secret_key(
            owner_sk,
            p2_delegated_puzzle_or_hidden_puzzle.DEFAULT_HIDDEN_PUZZLE_HASH,
        )
    )
    signature = AugSchemeMPL.sign(
        synthetic_secret_key,
        (
            delegated_puzzle.get_tree_hash()
            + genesis_coin.name()
            + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA
        ),
    )

    combined_spend_bundle: SpendBundle = SpendBundle.aggregate(
        [signed_tx.spend_bundle, SpendBundle(coin_spends, signature)]
    )

    if click.confirm("The transaction seems valid. Do you want to submit it?"):
        response = requests.post(
            f"{SINGLETON_GALLERY_API}/singletons/submit",
            json=combined_spend_bundle.to_json_dict(),
        )
        if response.status_code != 200:
            click.secho("Failed to submit NFT:", err=True, fg="red")
            click.secho(response.text, err=True, fg="red")
        else:
            launcher_coin_record = next(
                coin
                for coin in combined_spend_bundle.coin_spends
                if coin.coin.puzzle_hash == SINGLETON_LAUNCHER_HASH
            )
            click.secho("Your NFT has been submitted successfully!", fg="green")
            click.echo("Please wait a few minutes until the NFT has been added to the blockchain.")
            click.echo(
                f"You can inspect your NFT using the following link: {SINGLETON_GALLERY_FRONTEND}/singletons/{launcher_coin_record.coin.name()}"
            )


if __name__ == "__main__":
    cli()
