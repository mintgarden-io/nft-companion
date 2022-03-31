#!/usr/bin/env python
import asyncio
from typing import Optional, Tuple

import aiohttp
import click
import requests
from blspy import PrivateKey, AugSchemeMPL, G2Element
from click import FLOAT, INT
from clvm.casts import int_to_bytes

from chia.cmds.units import units
from chia.cmds.wallet_funcs import get_wallet
from chia.rpc.wallet_rpc_client import WalletRpcClient
from chia.types.blockchain_format.coin import Coin
from chia.types.blockchain_format.program import Program
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.spend_bundle import SpendBundle
from chia.util.config import load_config
from chia.util.default_root import DEFAULT_ROOT_PATH
from chia.util.ints import uint16, uint32
from chia.wallet.derive_keys import (
    master_sk_to_singleton_owner_sk,
    master_sk_to_wallet_sk,
)
from chia.wallet.puzzles import p2_delegated_puzzle_or_hidden_puzzle
from chia.wallet.puzzles.singleton_top_layer import SINGLETON_LAUNCHER_HASH
from chia.wallet.transaction_record import TransactionRecord
from ownable_singleton.drivers.ownable_singleton_driver import (
    SINGLETON_AMOUNT,
    create_unsigned_ownable_singleton,
    pay_to_singleton_puzzle,
    Owner,
    Royalty,
)

AGG_SIG_ME_ADDITIONAL_DATA_TESTNET10 = bytes.fromhex(
    "ae83525ba8d1dd3f09b277de18ca3e43fc0af20d20c4b3e92ef2a48bd291ccb2"
)

SINGLETON_GALLERY_API = "https://testnet.mintgarden.io/api"
SINGLETON_GALLERY_FRONTEND = "https://testnet.mintgarden.io"


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


def master_sk_to_wallet_puzhash(master_sk: PrivateKey) -> bytes32:
    wallet_sk = master_sk_to_wallet_sk(master_sk, uint32(0))
    wallet_puzzle = p2_delegated_puzzle_or_hidden_puzzle.puzzle_for_pk(
        wallet_sk.get_g1()
    )
    return wallet_puzzle.get_tree_hash()


async def get_singleton_wallet(fingerprint: int) -> Tuple[PrivateKey, int]:
    try:
        wallet_client: WalletRpcClient = await get_client()
        wallet_client_f, fingerprint = await get_wallet(wallet_client, fingerprint)

        private_key = await wallet_client.get_private_key(fingerprint)
        master_sk = PrivateKey.from_bytes(bytes.fromhex(private_key["sk"]))
        singleton_sk = master_sk_to_singleton_owner_sk(master_sk, uint32(0))

        return singleton_sk, fingerprint
    finally:
        wallet_client.close()
        await wallet_client.await_closed()


async def create_genesis_coin(
    fingerprint, amt, fee
) -> [TransactionRecord, PrivateKey, bytes32]:
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
        return signed_tx, singleton_sk, master_sk_to_wallet_puzhash(master_sk)
    finally:
        wallet_client.close()
        await wallet_client.await_closed()


async def create_p2_singleton_coin(
    fingerprint: Optional[int], launcher_id: str, amt: int, fee: int
) -> [TransactionRecord, Program, PrivateKey, bytes32]:
    try:
        wallet_client: WalletRpcClient = await get_client()
        wallet_client_f, fingerprint = await get_wallet(wallet_client, fingerprint)

        private_key = await wallet_client.get_private_key(fingerprint)
        master_sk = PrivateKey.from_bytes(bytes.fromhex(private_key["sk"]))
        singleton_sk = master_sk_to_singleton_owner_sk(master_sk, uint32(0))

        dummy_p2_singleton_puzzle = pay_to_singleton_puzzle(launcher_id, (b"0" * 32))

        signed_tx = await wallet_client.create_signed_transaction(
            [{"puzzle_hash": dummy_p2_singleton_puzzle.get_tree_hash(), "amount": amt}],
            fee=fee,
        )
        spent_coin = signed_tx.removals[0]

        p2_singleton_puzzle = pay_to_singleton_puzzle(
            bytes.fromhex(launcher_id), spent_coin.puzzle_hash
        )
        signed_tx = await wallet_client.create_signed_transaction(
            [{"puzzle_hash": p2_singleton_puzzle.get_tree_hash(), "amount": amt}],
            fee=fee,
            coins=signed_tx.removals,
        )

        return (
            signed_tx,
            p2_singleton_puzzle,
            singleton_sk,
            master_sk_to_wallet_puzhash(master_sk),
        )
    finally:
        wallet_client.close()
        await wallet_client.await_closed()


async def sign_offer(
    fingerprint: Optional[int], price: int, singleton_id: str
) -> [TransactionRecord, Program, PrivateKey]:
    try:
        wallet_client: WalletRpcClient = await get_client()
        wallet_client_f, fingerprint = await get_wallet(wallet_client, fingerprint)

        private_key = await wallet_client.get_private_key(fingerprint)
        master_sk = PrivateKey.from_bytes(bytes.fromhex(private_key["sk"]))
        singleton_sk = master_sk_to_singleton_owner_sk(master_sk, uint32(0))

        return AugSchemeMPL.sign(
            singleton_sk,
            int_to_bytes(price)
            + bytes.fromhex(singleton_id)
            + AGG_SIG_ME_ADDITIONAL_DATA_TESTNET10,
        )
    finally:
        wallet_client.close()
        await wallet_client.await_closed()


@click.group()
def cli():
    pass


@cli.command()
@click.option("--fingerprint", type=int, help="The fingerprint of the key to use")
def profile(fingerprint: int):
    singleton_sk: PrivateKey
    singleton_sk, _ = asyncio.get_event_loop().run_until_complete(
        get_singleton_wallet(fingerprint)
    )

    click.echo(
        f"Your singleton profile is {SINGLETON_GALLERY_FRONTEND}/profile/{bytes(singleton_sk.get_g1()).hex()}"
    )


@cli.command()
@click.option("--name", prompt=True, help="Your profile name")
@click.option("--fingerprint", type=int, help="The fingerprint of the key to use")
def update_profile(name: str, fingerprint: int):
    singleton_sk: PrivateKey
    singleton_sk, _ = asyncio.get_event_loop().run_until_complete(
        get_singleton_wallet(fingerprint)
    )

    public_key = singleton_sk.get_g1()
    signature = AugSchemeMPL.sign(
        singleton_sk,
        bytes(public_key) + bytes(name, "utf-8"),
    )

    if click.confirm(f"Do you want to set your profile name to {name}?"):
        response = requests.patch(
            f"{SINGLETON_GALLERY_API}/profile/{public_key}",
            json={"signature": bytes(signature).hex(), "name": name},
        )
        if response.status_code != 200:
            click.secho("Failed to update profile:", err=True, fg="red")
            click.secho(response.text, err=True, fg="red")
        else:
            click.secho("Your profile has been updated!", fg="green")
            click.echo(
                f"You can inspect it using the following link: {SINGLETON_GALLERY_FRONTEND}/profile/{public_key}"
            )


@cli.command()
@click.option("--name", prompt=True, help="The name of the NFT")
@click.option("--uri", prompt=True, help="The uri of the main NFT image")
@click.option(
    "-r",
    "--royalty",
    "royalty_percentage",
    type=INT,
    prompt=True,
    help="The percentage of each sale you want to receive as royalty.",
    default=0,
    show_default=True,
)
@click.option("--fingerprint", type=int, help="The fingerprint of the key to use")
@click.option(
    "--fee",
    type=FLOAT,
    required=True,
    default=0,
    show_default=True,
    help="The XCH fee to use for this transaction",
)
def create(name: str, uri: str, fingerprint: int, royalty_percentage: int, fee: int):
    if royalty_percentage > 99 or royalty_percentage < 0:
        click.secho(
            f"Royalty percentage has to be between 1 and 99.", err=True, fg="red"
        )
        return

    signed_tx: TransactionRecord
    owner_sk: PrivateKey
    wallet_puzzle_hash: bytes32
    (
        signed_tx,
        owner_sk,
        wallet_puzzle_hash,
    ) = asyncio.get_event_loop().run_until_complete(
        create_genesis_coin(fingerprint, SINGLETON_AMOUNT, fee)
    )
    genesis_coin: Coin = next(
        coin for coin in signed_tx.additions if coin.amount == SINGLETON_AMOUNT
    )
    genesis_puzzle = p2_delegated_puzzle_or_hidden_puzzle.puzzle_for_pk(
        owner_sk.get_g1()
    )
    creator = Owner(owner_sk.get_g1(), wallet_puzzle_hash)
    royalty = (
        Royalty(creator.puzzle_hash, royalty_percentage)
        if royalty_percentage > 0
        else None
    )

    coin_spends, delegated_puzzle = create_unsigned_ownable_singleton(
        genesis_coin, genesis_puzzle, creator, uri, name, version=2, royalty=royalty
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
            + AGG_SIG_ME_ADDITIONAL_DATA_TESTNET10
        ),
    )

    combined_spend_bundle: SpendBundle = SpendBundle.aggregate(
        [signed_tx.spend_bundle, SpendBundle(coin_spends, signature)]
    )

    if click.confirm("The transaction seems valid. Do you want to submit it?"):
        response = requests.post(
            f"{SINGLETON_GALLERY_API}/singletons/submit",
            json=combined_spend_bundle.to_json_dict(
                include_legacy_keys=False, exclude_modern_keys=False
            ),
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
            click.echo(
                "Please wait a few minutes until the NFT has been added to the blockchain."
            )
            click.echo(
                f"You can inspect your NFT using the following link: {SINGLETON_GALLERY_FRONTEND}/singletons/{launcher_coin_record.coin.name()}?pending=1"
            )


@cli.command()
@click.option("--launcher-id", prompt=True, help="The ID of the NFT")
@click.option(
    "--price",
    type=float,
    prompt=True,
    help="The price (in XCH) you want to offer for this NFT singleton",
)
@click.option("--fingerprint", type=int, help="The fingerprint of the key to use")
@click.option(
    "--fee",
    required=True,
    default=0,
    show_default=True,
    help="The XCH fee to use for this transaction",
)
def offer(launcher_id: str, price: float, fingerprint: Optional[int], fee: int):
    response = requests.get(f"{SINGLETON_GALLERY_API}/singletons/{launcher_id}")
    if response.status_code != 200:
        click.secho(
            f"Could not find an NFT with ID '{launcher_id}'", err=True, fg="red"
        )
        return
    singleton = response.json()
    name = singleton["name"]
    owner = singleton["owner"]

    price_in_mojo = int(price * units["chia"])

    try:
        signed_tx: TransactionRecord
        p2_singleton_puzzle: Program
        owner_sk: PrivateKey
        wallet_puzzle_hash: bytes32
        (
            signed_tx,
            p2_singleton_puzzle,
            owner_sk,
            wallet_puzzle_hash,
        ) = asyncio.get_event_loop().run_until_complete(
            create_p2_singleton_coin(fingerprint, launcher_id, price_in_mojo, fee)
        )
        p2_singleton_coin: Coin = next(
            coin
            for coin in signed_tx.additions
            if coin.puzzle_hash == p2_singleton_puzzle.get_tree_hash()
        )
    except TypeError:
        return

    new_owner_pubkey = owner_sk.get_g1()
    if owner == bytes(new_owner_pubkey).hex():
        click.secho(
            "This is your singleton, you can't create an offer for it.", fg="yellow"
        )
        return

    singleton_signature = AugSchemeMPL.sign(
        owner_sk,
        wallet_puzzle_hash
        + bytes.fromhex(singleton["singleton_id"])
        + AGG_SIG_ME_ADDITIONAL_DATA_TESTNET10,
    )
    payment_spend_bundle = SpendBundle.aggregate(
        [signed_tx.spend_bundle, SpendBundle([], singleton_signature)]
    )

    if click.confirm(
        f"You are offering {price} XCH for '{name}'. Do you want to submit it?"
    ):
        response = requests.post(
            f"{SINGLETON_GALLERY_API}/singletons/{launcher_id}/offers/submit",
            json={
                "payment_spend_bundle": payment_spend_bundle.to_json_dict(
                    include_legacy_keys=False, exclude_modern_keys=False
                ),
                "p2_singleton_coin": p2_singleton_coin.to_json_dict(),
                "p2_singleton_puzzle": bytes(p2_singleton_puzzle).hex(),
                "new_owner_pubkey": bytes(new_owner_pubkey).hex(),
                "new_owner_puzhash": wallet_puzzle_hash.hex(),
                "price": price_in_mojo,
            },
        )
        if response.status_code != 200:
            click.secho("Failed to submit offer:", err=True, fg="red")
            click.secho(response.text, err=True, fg="red")
        else:
            click.secho("Your offer has been submitted successfully!", fg="green")
            click.echo(
                f"You can inspect it using the following link: {SINGLETON_GALLERY_FRONTEND}/singletons/{launcher_id}"
            )


@cli.command()
@click.option("--launcher-id", prompt=True, help="The ID of the NFT")
@click.option("--offer-id", prompt=True, help="The ID of the offer you want to accept")
@click.option("--fingerprint", type=int, help="The fingerprint of the key to use")
def accept_offer(launcher_id: str, offer_id: str, fingerprint: Optional[int]):
    singleton_response = requests.get(
        f"{SINGLETON_GALLERY_API}/singletons/{launcher_id}"
    )
    if singleton_response.status_code != 200:
        click.secho(
            f"Could not find an NFT with ID '{launcher_id}'", err=True, fg="red"
        )
        return
    name = singleton_response.json()["name"]
    royalty_percentage = singleton_response.json()["royalty_percentage"]

    offer_response = requests.get(
        f"{SINGLETON_GALLERY_API}/singletons/{launcher_id}/offers/{offer_id}"
    )
    if offer_response.status_code != 200:
        click.secho(
            f"Could not find an offer with ID '{offer_id}' for NFT '{name}'.",
            err=True,
            fg="yellow",
        )
        return
    offer = offer_response.json()
    price = offer["price"]
    price_in_chia = price / units["chia"]

    price_signature: G2Element = asyncio.get_event_loop().run_until_complete(
        sign_offer(fingerprint, price, offer["singleton_id"])
    )

    royalty_text = (
        f" A share of {royalty_percentage}% of that price is sent to its creator."
        if royalty_percentage > 0
        else ""
    )
    if click.confirm(
        f"You are accepting {price_in_chia} XCH for '{name}'.{royalty_text} Do you want to submit it?"
    ):
        response = requests.post(
            f"{SINGLETON_GALLERY_API}/singletons/{launcher_id}/offers/{offer_id}/accept",
            json={
                "price_signature": bytes(price_signature).hex(),
            },
        )
        if response.status_code != 200:
            click.secho("Failed to accept offer:", err=True, fg="red")
            click.secho(response.text, err=True, fg="red")
        else:
            click.secho("You accepted the offer!", fg="green")
            click.echo(f"The payment is being sent to your wallet address.")


@cli.command()
@click.option("--launcher-id", prompt=True, help="The ID of the NFT")
@click.option("--offer-id", prompt=True, help="The ID of the offer you want to cancel")
@click.option("--fingerprint", type=int, help="The fingerprint of the key to use")
def cancel_offer(launcher_id: str, offer_id: str, fingerprint: Optional[int]):
    singleton_response = requests.get(
        f"{SINGLETON_GALLERY_API}/singletons/{launcher_id}"
    )
    if singleton_response.status_code != 200:
        click.secho(
            f"Could not find an NFT with ID '{launcher_id}'", err=True, fg="red"
        )
        return
    name = singleton_response.json()["name"]

    offer_response = requests.get(
        f"{SINGLETON_GALLERY_API}/singletons/{launcher_id}/offers/{offer_id}"
    )
    if offer_response.status_code != 200:
        click.secho(
            f"Could not find an offer with ID '{offer_id}' for NFT '{name}'.",
            err=True,
            fg="yellow",
        )
        return
    offer = offer_response.json()
    price = offer["price"]
    price_in_chia = price / units["chia"]

    singleton_sk: PrivateKey
    (singleton_sk, fingerprint) = asyncio.get_event_loop().run_until_complete(
        get_singleton_wallet(fingerprint)
    )
    if offer["new_owner_public_key"] != bytes(singleton_sk.get_g1()).hex():
        click.secho(f"This is not your offer.", err=True, fg="red")
        return

    price_signature: G2Element = asyncio.get_event_loop().run_until_complete(
        sign_offer(fingerprint, price, offer["singleton_id"])
    )

    if click.confirm(
        f"Do you want to cancel your offer of {price_in_chia} XCH for '{name}'?"
    ):
        response = requests.delete(
            f"{SINGLETON_GALLERY_API}/singletons/{launcher_id}/offers/{offer_id}",
            json={
                "price_signature": bytes(price_signature).hex(),
            },
        )
        if response.status_code != 200:
            click.secho("Failed to cancel offer:", err=True, fg="red")
            click.secho(response.text, err=True, fg="red")
        else:
            click.secho("You cancelled the offer.", fg="green")


if __name__ == "__main__":
    cli()
