#!/usr/bin/env python
import click
from blspy import G2Element, AugSchemeMPL, PrivateKey
from chia.consensus.default_constants import DEFAULT_CONSTANTS
from chia.wallet.puzzles import p2_delegated_puzzle_or_hidden_puzzle


@click.group()
def cli():
    pass


@cli.command()
@click.option('--delegated', is_flag=True, help='Sign using synthetic key (needed for delegated puzzle hash)')
@click.option('--puzzle_hash', prompt=True, help='The puzzle hash to be signed')
@click.option('--coin_id', prompt=True, help='The id of the coin to be spent')
@click.option('--secret_key', prompt=True, hide_input=True, help='The secret key to be used for signing')
def sign(delegated, puzzle_hash, coin_id, secret_key):
    puzzle_hash = bytes.fromhex(puzzle_hash)
    coin_id = bytes.fromhex(coin_id)
    secret_key = PrivateKey.from_bytes(bytes.fromhex(secret_key))

    if delegated:
        secret_key: PrivateKey = p2_delegated_puzzle_or_hidden_puzzle.calculate_synthetic_secret_key(  # noqa
            secret_key,
            p2_delegated_puzzle_or_hidden_puzzle.DEFAULT_HIDDEN_PUZZLE_HASH,
        )
    signature = AugSchemeMPL.sign(
        secret_key,
        (puzzle_hash + coin_id + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA),  # noqa
    )
    click.echo(f'signature: {signature}')


if __name__ == '__main__':
    cli()
