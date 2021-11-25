from typing import List, Optional

import pytest
from blspy import AugSchemeMPL, G2Element, PrivateKey
from cdv.test import CoinWrapper
from cdv.test import setup as setup_test
from clvm.casts import int_to_bytes

from chia.consensus.default_constants import DEFAULT_CONSTANTS
from chia.types.blockchain_format.coin import Coin
from chia.types.blockchain_format.program import Program
from chia.types.coin_spend import CoinSpend
from chia.types.spend_bundle import SpendBundle
from chia.util.ints import uint64
from chia.wallet.puzzles import singleton_top_layer, p2_delegated_puzzle_or_hidden_puzzle
from ownable_singleton.drivers.ownable_singleton_driver import (
    create_unsigned_ownable_singleton, create_inner_puzzle, create_buy_offer
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

            contribution_coin: Optional[CoinWrapper] = await alice.choose_coin(SINGLETON_AMOUNT)

            coin_id = contribution_coin.name()
            name = 'Curly Nonchalant Marmot'
            uri = 'https://example.com/curly-nonchalant-marmot.png'
            (coin_spends, delegated_puzzle) = create_unsigned_ownable_singleton(contribution_coin.as_coin(),
                                                                                contribution_coin.puzzle(),
                                                                                alice.pk_,
                                                                                uri, name)

            secret_key: PrivateKey = p2_delegated_puzzle_or_hidden_puzzle.calculate_synthetic_secret_key(  # noqa
                alice.sk_,
                p2_delegated_puzzle_or_hidden_puzzle.DEFAULT_HIDDEN_PUZZLE_HASH,
            )
            signature = AugSchemeMPL.sign(
                secret_key,
                (delegated_puzzle.get_tree_hash() + coin_id + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA),  # noqa
            )

            combined_spend = SpendBundle(coin_spends, signature)

            result = await network.push_tx(combined_spend)

            assert "error" not in result

            # Make sure there is a singleton owned by alice
            launcher_coin: Coin = singleton_top_layer.generate_launcher_coin(
                contribution_coin,
                SINGLETON_AMOUNT,
            )
            launcher_id = launcher_coin.name()
            alice_singleton_puzzle = singleton_top_layer.puzzle_for_singleton(launcher_id,
                                                                              create_inner_puzzle(alice.pk_))

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

            # remaining value is returned to the user
            filtered_result: List[Coin] = list(
                filter(
                    lambda addition: (addition.amount == contribution_coin.as_coin().amount - SINGLETON_AMOUNT) and (
                            addition.puzzle_hash == contribution_coin.as_coin().puzzle_hash),
                    result["additions"],
                )
            )
            assert len(filtered_result) == 1


            # Eve Spend
            singleton_coin: Coin = next(
                x for x in result['additions'] if x.puzzle_hash == alice_singleton_puzzle.get_tree_hash())

            launcher_coinsol = combined_spend.coin_spends[0]
            lineage_proof = singleton_top_layer.lineage_proof_for_coinsol(launcher_coinsol)

            payment_amount = 1000
            payment_coin: Optional[CoinWrapper] = await bob.choose_coin(payment_amount)

            # Alice prepares payment bundle
            (coin_spends, delegated_puzzle, new_owner_puzhash) = create_buy_offer(payment_coin.as_coin(),
                                                                                  payment_coin.puzzle(),
                                                                                  launcher_id,
                                                                                  lineage_proof,
                                                                                  singleton_coin,
                                                                                  alice.pk_,
                                                                                  bob.pk_,
                                                                                  payment_amount)

            synthetic_secret_key: PrivateKey = p2_delegated_puzzle_or_hidden_puzzle.calculate_synthetic_secret_key(
                # noqa
                bob.sk_,
                p2_delegated_puzzle_or_hidden_puzzle.DEFAULT_HIDDEN_PUZZLE_HASH,
            )

            delegated_puzzle_data = payment_coin.name() + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA
            signatures: List[G2Element] = [
                AugSchemeMPL.sign(bob.sk_, bytes(
                    new_owner_puzhash) + singleton_coin.name() + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA),
                AugSchemeMPL.sign(synthetic_secret_key,
                                  delegated_puzzle.get_tree_hash() + delegated_puzzle_data)]
            aggregated_signature = AugSchemeMPL.aggregate(signatures)

            assert AugSchemeMPL.aggregate_verify([bob.pk_,
                                                  synthetic_secret_key.get_g1()],
                                                 [bytes(
                                                     new_owner_puzhash) + singleton_coin.name() + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA,
                                                  delegated_puzzle.get_tree_hash() + delegated_puzzle_data],
                                                 aggregated_signature)
            buy_offer = SpendBundle(
                coin_spends,
                aggregated_signature,
            )

            # ALice signs the buy offer
            seller_signature = AugSchemeMPL.sign(alice.sk_, int_to_bytes(
                payment_amount) + singleton_coin.name() + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA)
            aggregated_signature = AugSchemeMPL.aggregate([buy_offer.aggregated_signature, seller_signature])

            owner_change_spend = SpendBundle(
                coin_spends,
                aggregated_signature,
            )

            result = await network.push_tx(owner_change_spend)

            assert "error" not in result

            bob_singleton_puzzle = singleton_top_layer.puzzle_for_singleton(launcher_id,
                                                                              create_inner_puzzle(bob.pk_))
            # Make sure there is a singleton owned by bob
            filtered_result: List[Coin] = list(
                filter(
                    lambda addition: (addition.amount == SINGLETON_AMOUNT)
                                     and (
                                             addition.puzzle_hash == bob_singleton_puzzle.get_tree_hash()
                                     ),
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
