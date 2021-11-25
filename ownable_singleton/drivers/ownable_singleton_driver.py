from pathlib import Path
from typing import Tuple, List

import cdv.clibs as std_lib
from blspy import G1Element
from cdv.util.load_clvm import load_clvm

from chia.types.blockchain_format.coin import Coin
from chia.types.blockchain_format.program import Program
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.coin_spend import CoinSpend
from chia.types.condition_opcodes import ConditionOpcode
from chia.util.ints import uint64
from chia.wallet.lineage_proof import LineageProof
from chia.wallet.puzzles import (
    p2_conditions,
    p2_delegated_puzzle_or_hidden_puzzle,
    singleton_top_layer,
)
from chia.wallet.puzzles.singleton_top_layer import SINGLETON_MOD_HASH, SINGLETON_LAUNCHER_HASH
from chia.wallet.util.debug_spend_bundle import disassemble

clibs_path: Path = Path(std_lib.__file__).parent
OWNABLE_SINGLETON_MOD: Program = load_clvm(
    "ownable_singleton.clsp", "ownable_singleton.clsp", search_paths=[clibs_path])
P2_SINGLETON_OR_CANCEL_MOD: Program = load_clvm(
    "p2_singleton_or_cancel.clsp", "ownable_singleton.clsp", search_paths=[clibs_path])
SINGLETON_AMOUNT: uint64 = 1023


def pay_to_singleton_puzzle(launcher_id: bytes32, cancel_puzhash: bytes32) -> Program:
    return P2_SINGLETON_OR_CANCEL_MOD.curry(SINGLETON_MOD_HASH, launcher_id, SINGLETON_LAUNCHER_HASH, cancel_puzhash)


def create_inner_puzzle(owner_pubkey: G1Element):
    return OWNABLE_SINGLETON_MOD.curry(owner_pubkey,
                                       p2_delegated_puzzle_or_hidden_puzzle.puzzle_for_pk(owner_pubkey).get_tree_hash(),
                                       OWNABLE_SINGLETON_MOD.get_tree_hash())


def create_unsigned_ownable_singleton(
        coin: Coin, puzzle: Program, owner_pubkey: G1Element, uri: str, name: str, fee: uint64 = 0) \
        -> Tuple[List[CoinSpend], Program]:
    inner_puzzle = create_inner_puzzle(owner_pubkey)
    comment = [("uri", uri), ("name", name), ("creator", owner_pubkey)]

    conditions, launcher_coinsol = singleton_top_layer.launch_conditions_and_coinsol(coin, inner_puzzle, comment,
                                                                                     SINGLETON_AMOUNT)

    conditions.append(Program.to(
        [
            ConditionOpcode.CREATE_COIN,
            coin.puzzle_hash,
            coin.amount - SINGLETON_AMOUNT - fee,
        ])
    )
    delegated_puzzle: Program = p2_conditions.puzzle_for_conditions(conditions)  # noqa
    full_solution: Program = p2_delegated_puzzle_or_hidden_puzzle.solution_for_conditions(conditions)  # noqa

    starting_coinsol: CoinSpend = CoinSpend(
        coin,
        puzzle,
        full_solution,
    )

    return [launcher_coinsol, starting_coinsol], delegated_puzzle


def create_buy_offer(
        payment_coin: Coin, puzzle: Program, launcher_id: bytes32, lineage_proof: LineageProof, singleton_coin: Coin,
        current_owner_pubkey: G1Element, new_owner_pubkey: G1Element, payment_amount: uint64, fee: uint64 = 0
) -> Tuple[List[CoinSpend], Program, bytes32]:
    p2_singleton_puzzle: Program = pay_to_singleton_puzzle(launcher_id, payment_coin.puzzle_hash)

    conditions = [(Program.to(
        [
            ConditionOpcode.CREATE_COIN,
            p2_singleton_puzzle.get_tree_hash(),
            payment_amount,
        ])
    ), (Program.to(
        [
            ConditionOpcode.CREATE_COIN,
            payment_coin.puzzle_hash,
            payment_coin.amount - payment_amount - fee,
        ])
    )]
    delegated_puzzle: Program = p2_conditions.puzzle_for_conditions(conditions)  # noqa
    full_solution: Program = p2_delegated_puzzle_or_hidden_puzzle.solution_for_conditions(conditions)  # noqa

    starting_coinsol: CoinSpend = CoinSpend(
        payment_coin,
        puzzle,
        full_solution,
    )

    singleton_inner_puzzle = create_inner_puzzle(current_owner_pubkey)

    p2_singleton_coin = Coin(payment_coin.name(), p2_singleton_puzzle.get_tree_hash(), payment_amount)
    p2_singleton_solution = Program.to(
        [singleton_inner_puzzle.get_tree_hash(), p2_singleton_coin.name(), new_owner_pubkey])

    p2_singleton_coinsol: CoinSpend = CoinSpend(
        p2_singleton_coin,
        p2_singleton_puzzle,
        p2_singleton_solution
    )

    singleton_puzzle = singleton_top_layer.puzzle_for_singleton(launcher_id, singleton_inner_puzzle)

    new_owner_puzhash: bytes32 = p2_delegated_puzzle_or_hidden_puzzle.puzzle_for_pk(new_owner_pubkey).get_tree_hash()
    inner_solution: Program = Program.to(
        [new_owner_pubkey, new_owner_puzhash, payment_amount, p2_singleton_coin.name()])

    singleton_solution: Program = singleton_top_layer.solution_for_singleton(
        lineage_proof,
        singleton_coin.amount,
        inner_solution,
    )

    singleton_coinsol: CoinSpend = CoinSpend(
        singleton_coin,
        singleton_puzzle,
        singleton_solution
    )

    return [p2_singleton_coinsol, starting_coinsol, singleton_coinsol], delegated_puzzle, new_owner_puzhash
