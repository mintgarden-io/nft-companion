from typing import List, Optional

import pytest
from blspy import AugSchemeMPL, G2Element, PrivateKey
from cdv.test import CoinWrapper
from cdv.test import setup as setup_test
from clvm.casts import int_to_bytes

from chia.consensus.default_constants import DEFAULT_CONSTANTS
from chia.types.blockchain_format.coin import Coin
from chia.types.condition_opcodes import ConditionOpcode
from chia.types.spend_bundle import SpendBundle
from chia.util.ints import uint64, uint32
from chia.wallet.derive_keys import master_sk_to_singleton_owner_sk
from chia.wallet.puzzles import (
    singleton_top_layer,
    p2_delegated_puzzle_or_hidden_puzzle,
)
from ownable_singleton.drivers.ownable_singleton_driver import (
    create_unsigned_ownable_singleton,
    create_inner_puzzle,
    create_buy_offer,
    pay_to_singleton_puzzle,
)

SINGLETON_AMOUNT: uint64 = 1023


class TestOwnableSingleton:
    @pytest.fixture(scope="function")
    async def setup(self):
        network, alice, bob = await setup_test()
        await network.farm_block()
        yield network, alice, bob

    @pytest.mark.asyncio
    async def test_singleton_creation(self, setup):
        network, alice, bob = setup
        try:
            await network.farm_block(farmer=alice)
            await network.farm_block(farmer=bob)

            contribution_coin: Optional[CoinWrapper] = await alice.choose_coin(
                SINGLETON_AMOUNT
            )

            alice_singleton_sk = master_sk_to_singleton_owner_sk(alice.sk_, uint32(0))
            singleton_wallet_puzzle = (
                p2_delegated_puzzle_or_hidden_puzzle.puzzle_for_pk(
                    alice_singleton_sk.get_g1()
                )
            )

            genesis_create_spend = await alice.spend_coin(
                contribution_coin,
                pushtx=False,
                custom_conditions=[
                    [
                        ConditionOpcode.CREATE_COIN,
                        singleton_wallet_puzzle.get_tree_hash(),
                        SINGLETON_AMOUNT,
                    ]
                ],
            )

            genesis_coin = Coin(
                parent_coin_info=contribution_coin.as_coin().name(),
                puzzle_hash=singleton_wallet_puzzle.get_tree_hash(),
                amount=SINGLETON_AMOUNT,
            )
            genesis_coin_puzzle = singleton_wallet_puzzle

            name = "Curly Nonchalant Marmot"
            uri = "https://example.com/curly-nonchalant-marmot.png"
            (coin_spends, delegated_puzzle) = create_unsigned_ownable_singleton(
                genesis_coin,
                genesis_coin_puzzle,
                alice_singleton_sk.get_g1(),
                uri,
                name,
            )

            secret_key: PrivateKey = (
                p2_delegated_puzzle_or_hidden_puzzle.calculate_synthetic_secret_key(
                    alice_singleton_sk,
                    p2_delegated_puzzle_or_hidden_puzzle.DEFAULT_HIDDEN_PUZZLE_HASH,
                )
            )
            signature = AugSchemeMPL.sign(
                secret_key,
                (
                    delegated_puzzle.get_tree_hash()
                    + genesis_coin.name()
                    + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA
                ),
            )

            singleton_spend = SpendBundle(coin_spends, signature)
            combined_spend = SpendBundle.aggregate(
                [genesis_create_spend, singleton_spend]
            )

            result = await network.push_tx(combined_spend)

            assert "error" not in result

            # Make sure there is a singleton owned by alice
            launcher_coin: Coin = singleton_top_layer.generate_launcher_coin(
                genesis_coin,
                SINGLETON_AMOUNT,
            )
            launcher_id = launcher_coin.name()
            alice_singleton_puzzle = singleton_top_layer.puzzle_for_singleton(
                launcher_id, create_inner_puzzle(alice_singleton_sk.get_g1())
            )

            # singleton coin is added and owned by alice
            filtered_result: List[Coin] = list(
                filter(
                    lambda addition: (addition.amount == SINGLETON_AMOUNT)
                    and (
                        addition.puzzle_hash == alice_singleton_puzzle.get_tree_hash()
                    ),
                    result["additions"],
                )
            )
            assert len(filtered_result) == 1

            # Eve Spend
            singleton_coin: Coin = next(
                x
                for x in result["additions"]
                if x.puzzle_hash == alice_singleton_puzzle.get_tree_hash()
            )

            launcher_coinsol = singleton_spend.coin_spends[0]
            lineage_proof = singleton_top_layer.lineage_proof_for_coinsol(
                launcher_coinsol
            )

            payment_amount = 10000
            payment_coin: Optional[CoinWrapper] = await bob.choose_coin(payment_amount)

            p2_singleton_puzzle = pay_to_singleton_puzzle(
                launcher_id, payment_coin.puzzle_hash
            )

            payment_coin_spend = await bob.spend_coin(
                payment_coin,
                pushtx=False,
                custom_conditions=[
                    [
                        ConditionOpcode.CREATE_COIN,
                        p2_singleton_puzzle.get_tree_hash(),
                        payment_amount,
                    ]
                ],
            )
            p2_singleton_coin = Coin(
                parent_coin_info=payment_coin.as_coin().name(),
                puzzle_hash=p2_singleton_puzzle.get_tree_hash(),
                amount=payment_amount,
            )

            bob_singleton_sk = master_sk_to_singleton_owner_sk(bob.sk_, uint32(0))

            # Bob prepares payment bundle
            (coin_spends, new_owner_puzhash) = create_buy_offer(
                p2_singleton_coin,
                p2_singleton_puzzle,
                launcher_id,
                lineage_proof,
                singleton_coin,
                alice_singleton_sk.get_g1(),
                bob_singleton_sk.get_g1(),
                payment_amount,
            )

            signatures: List[G2Element] = [
                AugSchemeMPL.sign(
                    bob_singleton_sk,
                    bytes(new_owner_puzhash)
                    + singleton_coin.name()
                    + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA,
                ),
            ]
            aggregated_signature = AugSchemeMPL.aggregate(signatures)

            assert AugSchemeMPL.aggregate_verify(
                [bob_singleton_sk.get_g1()],
                [
                    bytes(new_owner_puzhash)
                    + singleton_coin.name()
                    + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA
                ],
                aggregated_signature,
            )
            buy_offer = SpendBundle.aggregate(
                [
                    payment_coin_spend,
                    SpendBundle(
                        coin_spends,
                        aggregated_signature,
                    ),
                ]
            )

            # ALice signs the buy offer
            seller_signature = AugSchemeMPL.sign(
                alice_singleton_sk,
                int_to_bytes(payment_amount)
                + singleton_coin.name()
                + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA,
            )
            aggregated_signature = AugSchemeMPL.aggregate(
                [buy_offer.aggregated_signature, seller_signature]
            )

            owner_change_spend = SpendBundle(
                buy_offer.coin_spends,
                aggregated_signature,
            )

            result = await network.push_tx(owner_change_spend)

            assert "error" not in result

            bob_singleton_puzzle = singleton_top_layer.puzzle_for_singleton(
                launcher_id, create_inner_puzzle(bob_singleton_sk.get_g1())
            )
            # Make sure there is a singleton owned by bob
            filtered_result: List[Coin] = list(
                filter(
                    lambda addition: (addition.amount == SINGLETON_AMOUNT)
                    and (addition.puzzle_hash == bob_singleton_puzzle.get_tree_hash()),
                    result["additions"],
                )
            )
            assert len(filtered_result) == 1

            # print(network.sim.block_height)
            # print(network.sim.block_height)
            # launcher_coins = await network.sim_client.get_coin_records_by_puzzle_hash(launcher_coin.puzzle_hash)
            # print(launcher_coins)
            # puzzle_and_solution = await network.sim_client.get_puzzle_and_solution(launcher_coins[0].name,
            #                                                                        launcher_coins[0].spent_block_index)
            # solution = Program.from_bytes(bytes(puzzle_and_solution.solution))
            # print(solution.as_python()[2][0].decode('utf-8'))
        finally:
            await network.close()
