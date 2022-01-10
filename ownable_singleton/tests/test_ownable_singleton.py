from typing import List, Optional

import pytest
from blspy import AugSchemeMPL, G2Element, PrivateKey, G1Element
from cdv.test import CoinWrapper, Wallet
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
    Owner,
    Royalty,
)

SINGLETON_AMOUNT: uint64 = 1023


def wallet_to_owner(wallet: Wallet) -> Owner:
    wallet_singleton_sk = master_sk_to_singleton_owner_sk(wallet.sk_, uint32(0))
    singleton_wallet_puzzle = p2_delegated_puzzle_or_hidden_puzzle.puzzle_for_pk(
        wallet_singleton_sk.get_g1()
    )

    return Owner(wallet_singleton_sk.get_g1(), singleton_wallet_puzzle.get_tree_hash())


async def create_singleton_spend_bundle(
    contribution_coin: Coin, creator_wallet, version, royalty: Royalty
):
    creator = wallet_to_owner(creator_wallet)

    genesis_create_spend = await creator_wallet.spend_coin(
        contribution_coin,
        pushtx=False,
        amt=SINGLETON_AMOUNT,
        remain=creator_wallet,
        custom_conditions=[
            [
                ConditionOpcode.CREATE_COIN,
                creator.puzzle_hash,
                SINGLETON_AMOUNT,
            ]
        ],
    )
    genesis_coin = Coin(
        parent_coin_info=contribution_coin.as_coin().name(),
        puzzle_hash=creator.puzzle_hash,
        amount=SINGLETON_AMOUNT,
    )
    genesis_coin_puzzle = p2_delegated_puzzle_or_hidden_puzzle.puzzle_for_pk(
        creator.public_key
    )
    name = "Curly Nonchalant Marmot"
    uri = "https://example.com/curly-nonchalant-marmot.png"
    (coin_spends, delegated_puzzle) = create_unsigned_ownable_singleton(
        genesis_coin,
        genesis_coin_puzzle,
        creator,
        uri,
        name,
        version,
        royalty,
    )

    creator_singleton_sk = master_sk_to_singleton_owner_sk(
        creator_wallet.sk_, uint32(0)
    )
    synthetic_secret_key: PrivateKey = (
        p2_delegated_puzzle_or_hidden_puzzle.calculate_synthetic_secret_key(
            creator_singleton_sk,
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
    singleton_spend = SpendBundle(coin_spends, signature)
    combined_spend = SpendBundle.aggregate([genesis_create_spend, singleton_spend])
    return combined_spend, genesis_coin, singleton_spend.coin_spends[0]


async def get_singleton_puzzle_owned_by_user(
    result, launcher_id, user, version, royalty
):
    owner = wallet_to_owner(user)

    inner_puzzle = create_inner_puzzle(version, owner, royalty)
    user_singleton_puzzle = singleton_top_layer.puzzle_for_singleton(
        launcher_id, inner_puzzle
    )
    # singleton coin is added and owned by user
    filtered_result: List[Coin] = list(
        filter(
            lambda addition: (addition.amount == SINGLETON_AMOUNT)
            and (addition.puzzle_hash == user_singleton_puzzle.get_tree_hash()),
            result["additions"],
        )
    )
    assert len(filtered_result) == 1
    return user_singleton_puzzle


async def create_buy_offer_for_user(
    current_owner_wallet: Wallet,
    buyer_wallet: Wallet,
    launcher_coinsol,
    launcher_id,
    payment_amount,
    payment_coin,
    singleton_coin,
    version,
    royalty,
) -> SpendBundle:
    current_owner = wallet_to_owner(current_owner_wallet)
    buyer = wallet_to_owner(buyer_wallet)

    buyer_singleton_sk = master_sk_to_singleton_owner_sk(buyer_wallet.sk_, uint32(0))

    lineage_proof = singleton_top_layer.lineage_proof_for_coinsol(launcher_coinsol)
    p2_singleton_puzzle = pay_to_singleton_puzzle(launcher_id, payment_coin.puzzle_hash)
    payment_coin_spend = await buyer_wallet.spend_coin(
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
    # Bob prepares payment bundle
    coin_spends = create_buy_offer(
        p2_singleton_coin,
        p2_singleton_puzzle,
        launcher_id,
        lineage_proof,
        singleton_coin,
        current_owner,
        buyer,
        payment_amount,
        version,
        royalty,
    )
    signatures: List[G2Element] = [
        AugSchemeMPL.sign(
            buyer_singleton_sk,
            buyer.puzzle_hash
            + singleton_coin.name()
            + DEFAULT_CONSTANTS.AGG_SIG_ME_ADDITIONAL_DATA,
        ),
    ]
    aggregated_signature = AugSchemeMPL.aggregate(signatures)
    assert AugSchemeMPL.aggregate_verify(
        [buyer.public_key],
        [
            buyer.puzzle_hash
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
    return buy_offer


async def accept_buy_offer(singleton_coin, buy_offer, seller, payment_amount):
    seller_singleton_sk = master_sk_to_singleton_owner_sk(seller.sk_, uint32(0))

    # ALice signs the buy offer
    seller_signature = AugSchemeMPL.sign(
        seller_singleton_sk,
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
    return owner_change_spend


testdata = [
    [1, 0],
    [2, 0],
    [2, 10],
]


class TestOwnableSingleton:
    @pytest.fixture(scope="function")
    async def setup(self):
        network, alice, bob = await setup_test()
        await network.farm_block()
        yield network, alice, bob

    @pytest.mark.asyncio
    @pytest.mark.parametrize("version,royalty_percentage", testdata)
    async def test_singleton_creation(self, setup, version, royalty_percentage):
        network, alice, bob = setup
        try:
            await network.farm_block(farmer=alice)

            contribution_coin: Optional[CoinWrapper] = await alice.choose_coin(
                SINGLETON_AMOUNT
            )
            royalty = (
                Royalty(alice.puzzle_hash, royalty_percentage)
                if royalty_percentage
                else None
            )

            (
                combined_spend,
                genesis_coin,
                launcher_coinsol,
            ) = await create_singleton_spend_bundle(
                contribution_coin, alice, version, royalty
            )

            result = await network.push_tx(combined_spend)

            assert "error" not in result

            # Make sure there is a singleton owned by alice
            launcher_coin: Coin = singleton_top_layer.generate_launcher_coin(
                genesis_coin,
                SINGLETON_AMOUNT,
            )
            launcher_id = launcher_coin.name()

            await get_singleton_puzzle_owned_by_user(
                result, launcher_id, alice, version, royalty
            )

        finally:
            await network.close()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("version,royalty_percentage", testdata)
    async def test_singleton_buy_offer(self, setup, version, royalty_percentage):
        network, alice, bob = setup
        try:
            await network.farm_block(farmer=alice)
            await network.farm_block(farmer=bob)

            contribution_coin: Optional[CoinWrapper] = await alice.choose_coin(
                SINGLETON_AMOUNT
            )
            royalty = (
                Royalty(alice.puzzle_hash, royalty_percentage)
                if royalty_percentage
                else None
            )
            alice_initial_balance = alice.balance()

            (
                combined_spend,
                genesis_coin,
                launcher_coinsol,
            ) = await create_singleton_spend_bundle(
                contribution_coin, alice, version, royalty
            )

            result = await network.push_tx(combined_spend)

            assert "error" not in result

            # Make sure there is a singleton owned by alice
            launcher_coin: Coin = singleton_top_layer.generate_launcher_coin(
                genesis_coin,
                SINGLETON_AMOUNT,
            )
            launcher_id = launcher_coin.name()

            alice_singleton_puzzle = await get_singleton_puzzle_owned_by_user(
                result, launcher_id, alice, version, royalty
            )

            assert alice.balance() == alice_initial_balance - SINGLETON_AMOUNT

            # Eve Spend
            singleton_coin: Coin = next(
                x
                for x in result["additions"]
                if x.puzzle_hash == alice_singleton_puzzle.get_tree_hash()
            )

            payment_amount = 10000

            payment_coin: Optional[CoinWrapper] = await bob.choose_coin(payment_amount)

            buy_offer = await create_buy_offer_for_user(
                alice,
                bob,
                launcher_coinsol,
                launcher_id,
                payment_amount,
                payment_coin,
                singleton_coin,
                version,
                royalty,
            )

            accepted_buy_offer = await accept_buy_offer(
                singleton_coin, buy_offer, alice, payment_amount
            )

            result = await network.push_tx(accepted_buy_offer)

            assert "error" not in result

            owner = wallet_to_owner(bob)

            inner_puzzle = create_inner_puzzle(version, owner, royalty)
            bob_singleton_puzzle = singleton_top_layer.puzzle_for_singleton(
                launcher_id, inner_puzzle
            )
            # singleton coin is added and owned by user
            filtered_result: List[Coin] = list(
                filter(
                    lambda addition: (addition.amount == SINGLETON_AMOUNT)
                    and (addition.puzzle_hash == bob_singleton_puzzle.get_tree_hash()),
                    result["additions"],
                )
            )
            assert len(filtered_result) == 1

            assert alice.balance() == alice_initial_balance - SINGLETON_AMOUNT + (
                payment_amount * royalty_percentage / 100
            )
            print(alice.usable_coins)

        finally:
            await network.close()
