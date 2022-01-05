from pathlib import Path
from typing import Tuple, List, Optional

import cdv.clibs as std_lib
from blspy import G1Element
from cdv.util.load_clvm import load_clvm
from clvm.casts import int_from_bytes

from chia.types.blockchain_format.coin import Coin
from chia.types.blockchain_format.program import Program
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.coin_spend import CoinSpend
from chia.util.ints import uint64
from chia.wallet.lineage_proof import LineageProof
from chia.wallet.puzzles import (
    p2_conditions,
    p2_delegated_puzzle_or_hidden_puzzle,
    singleton_top_layer,
)
from chia.wallet.puzzles.singleton_top_layer import (
    SINGLETON_MOD_HASH,
    SINGLETON_LAUNCHER_HASH,
)

clibs_path: Path = Path(std_lib.__file__).parent

OWNABLE_SINGLETON_MOD_V1: Program = load_clvm(
    "ownable_singleton_v1.clsp", "ownable_singleton.clsp", search_paths=[clibs_path]
)
OWNABLE_SINGLETON_MOD_V2: Program = load_clvm(
    "ownable_singleton_v2.clsp", "ownable_singleton.clsp", search_paths=[clibs_path]
)
P2_SINGLETON_OR_CANCEL_MOD: Program = load_clvm(
    "p2_singleton_or_cancel.clsp", "ownable_singleton.clsp", search_paths=[clibs_path]
)
SINGLETON_AMOUNT: uint64 = 1023


class Owner:
    def __init__(self, public_key: G1Element, puzzle_hash: bytes32):
        self.public_key = public_key
        self.puzzle_hash = puzzle_hash

    @staticmethod
    def from_bytes_list(owner_array: List[bytes32]):
        return Owner(G1Element.from_bytes(owner_array[0]), owner_array[1])


class Royalty:
    def __init__(self, creator_puzhash: bytes32, percentage: int):
        self.creator_puzhash = creator_puzhash
        self.percentage = percentage

    @staticmethod
    def from_bytes_list(royalty_list: List[bytes32]):
        return Royalty(royalty_list[0], int_from_bytes(royalty_list[1]))


def pay_to_singleton_puzzle(launcher_id: bytes32, cancel_puzhash: bytes32) -> Program:
    return P2_SINGLETON_OR_CANCEL_MOD.curry(
        SINGLETON_MOD_HASH, launcher_id, SINGLETON_LAUNCHER_HASH, cancel_puzhash
    )


def create_inner_puzzle(version: int, owner: Owner, royalty: Optional[Royalty] = None):
    if version == 1:
        if royalty is not None:
            raise f"Version 1 does not support royalties"

        return OWNABLE_SINGLETON_MOD_V1.curry(
            owner.public_key,
            owner.puzzle_hash,
            OWNABLE_SINGLETON_MOD_V1.get_tree_hash(),
        )
    elif version == 2:
        return OWNABLE_SINGLETON_MOD_V2.curry(
            [
                owner.public_key,
                owner.puzzle_hash,
            ],
            [royalty.creator_puzhash, royalty.percentage] if royalty else [],
            OWNABLE_SINGLETON_MOD_V2.get_tree_hash(),
        )
    else:
        raise f"Unsupported version: {version}"


def create_inner_solution(
    version: int, new_owner: Owner, payment_amount: int, payment_id: bytes32
) -> Program:
    if version == 1:
        return Program.to(
            [
                new_owner.public_key,
                new_owner.puzzle_hash,
                payment_amount,
                payment_id,
            ]
        )
    elif version == 2:
        return Program.to(
            [
                [new_owner.public_key, new_owner.puzzle_hash],
                [payment_amount, payment_id],
            ]
        )


def create_unsigned_ownable_singleton(
    genesis_coin: Coin,
    genesis_coin_puzzle: Program,
    creator: Owner,
    uri: str,
    name: str,
    version=1,
    royalty: Optional[Royalty] = None,
) -> Tuple[List[CoinSpend], Program]:
    comment = [
        ("uri", uri),
        ("name", name),
        ("creator", [creator.public_key, creator.puzzle_hash] if version == 2 else creator.public_key),
        ("version", version),
    ]

    inner_puzzle = create_inner_puzzle(version, creator, royalty)
    if royalty:
        comment.append(
            (
                "royalty",
                [royalty.creator_puzhash, royalty.percentage],
            )
        )

    assert genesis_coin.amount == SINGLETON_AMOUNT

    conditions, launcher_coinsol = singleton_top_layer.launch_conditions_and_coinsol(
        genesis_coin, inner_puzzle, comment, SINGLETON_AMOUNT
    )

    delegated_puzzle: Program = p2_conditions.puzzle_for_conditions(conditions)
    full_solution: Program = (
        p2_delegated_puzzle_or_hidden_puzzle.solution_for_conditions(conditions)
    )

    starting_coinsol: CoinSpend = CoinSpend(
        genesis_coin,
        genesis_coin_puzzle,
        full_solution,
    )

    return [launcher_coinsol, starting_coinsol], delegated_puzzle


def create_buy_offer(
    p2_singleton_coin: Coin,
    p2_singleton_puzzle: Program,
    launcher_id: bytes32,
    lineage_proof: LineageProof,
    singleton_coin: Coin,
    current_owner: Owner,
    new_owner: Owner,
    payment_amount: uint64,
    version=1,
    royalty: Optional[Royalty] = None,
) -> List[CoinSpend]:
    singleton_inner_puzzle = create_inner_puzzle(version, current_owner, royalty)

    p2_singleton_solution = Program.to(
        [
            singleton_inner_puzzle.get_tree_hash(),
            p2_singleton_coin.name(),
            new_owner.public_key,
        ]
    )

    p2_singleton_coinsol: CoinSpend = CoinSpend(
        p2_singleton_coin, p2_singleton_puzzle, p2_singleton_solution
    )

    singleton_puzzle = singleton_top_layer.puzzle_for_singleton(
        launcher_id, singleton_inner_puzzle
    )

    inner_solution = create_inner_solution(
        version, new_owner, payment_amount, p2_singleton_coin.name()
    )

    singleton_solution: Program = singleton_top_layer.solution_for_singleton(
        lineage_proof,
        singleton_coin.amount,
        inner_solution,
    )

    singleton_coinsol: CoinSpend = CoinSpend(
        singleton_coin, singleton_puzzle, singleton_solution
    )

    return [p2_singleton_coinsol, singleton_coinsol]
