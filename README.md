<p align="center">
  <a href="https://xch.gallery">
    <img src="https://xch.gallery/pflanz_128.png" alt="xch.gallery logo" width="128" height="128">
  </a>
</p>

<h3 align="center">NFT Companion</h3>

<div align="center">
  Create and trade NFTs on <a href="https://xch.gallery">xch.gallery</a> and the Chia blockchain.
</div>

## Installation

1. Clone the repository
```shell
git clone https://github.com/xch-gallery/nft-companion.git
cd nft-companion
```

2.LINUX install: Run the install script and activate the virtual environment in Linux
```shell
sh install.sh
. ./venv/bin/activate
```


2.WIN10 install: Run the install script and activate the virtual environment in Win10
```
git clone https://github.com/xch-gallery/nft-companion
cd nft-companion
./install.ps1

./venv/Scripts/activate

Create NFT in Win10
python nft.py create --name "Curly Nonchalant Marmot" --uri "https://example.com/curly-nonchalant-marmot.png"

```

## Create a new NFT singleton

The `create` command can be used to create a new NFT singleton using the Chia light wallet.
It requires a running wallet on your computer.

```shell
$ python3 nft.py create --help
Usage: nft.py create [OPTIONS]

Options:
  --name TEXT            The name of the NFT
  --uri TEXT             The uri of the main NFT image
  --royalty INTEGER      The royalty percentage [default: 0]
  --fingerprint INTEGER  The fingerprint of the key to use [optional]
  --fee INTEGER          The XCH fee to use for this transaction  [default: 0]
  --help                 Show this message and exit.
```

The following example shows the creation of an example NFT singleton.

```shell
$ python3 nft.py create --name "Curly Nonchalant Marmot" --uri "https://example.com/curly-nonchalant-marmot.png"
The transaction seems valid. Do you want to submit it? [y/N]: y
The NFT has been submitted successfully!
Please wait a few minutes for the NFT to be finalized.
You can inspect your NFT using the following link: https://xch.gallery/singletons/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx


Accept a offer:
$python3 nft.py accept-offer --offer-id 8 --launcher-id "4e4d4bf47b26e233de96da85d132617e5aac4d8087cf61e0f17a2a7d92a1d51e" --fingerprint "3405833834"

```

## Make a buy offer for a NFT singleton

The `offer` command can be used to make an offer to buy a NFT singleton.
It requires a running wallet on your computer.

```shell
$ python3 nft.py offer --help
Usage: nft.py offer [OPTIONS]

Options:
  --launcher-id TEXT     The ID of the NFT
  --price FLOAT          The price (in XCH) you want to offer for this NFT singleton
  --fingerprint INTEGER  The fingerprint of the key to use [optional]
  --fee INTEGER          The XCH fee to use for this transaction  [default: 0]
  --help                 Show this message and exit.
```

Here is an example of making a buy offer.

```shell
$  python3 nft.py offer --price 0.11 --launcher-id "356eb19da1fac4490c8f83e39788d5989cc0db5a2eaf8285a58cd7f4ebe07501"
You are offering 0.11 XCH for 'The fox'. Do you want to submit it? [y/N]: y
Your offer has been submitted successfully!
You can inspect it using the following link: https://xch.gallery/singletons/356eb19da1fac4490c8f83e39788d5989cc0db5a2eaf8285a58cd7f4ebe07501
```

## Accept a buy offer for a NFT singleton

The `accept-offer` command can be used to accept a buy offer.
It requires a running wallet on your computer.

```shell
$ python3 nft.py accept-offer --help
Usage: nft.py accept-offer [OPTIONS]

Options:
  --launcher-id TEXT     The ID of the NFT
  --offer-id TEXT        The ID of the offer you want to accept
  --fingerprint INTEGER  The fingerprint of the key to use [optional]
  --help                 Show this message and exit.
```

Here is an example of accepting a buy offer.

```shell
$ python3 nft.py accept-offer --offer-id 16 --launcher-id "356eb19da1fac4490c8f83e39788d5989cc0db5a2eaf8285a58cd7f4ebe07501"
You are accepting 0.11 XCH for 'The fox'. Do you want to submit it? [y/N]: y
You accepted the offer!
The payment is being sent to your singleton wallet address.
```

## Cancel a buy offer for a NFT singleton

The `cancel-offer` command can be used to cancel one of your buy offers.
It requires a running wallet on your computer.

```shell
$ python3 nft.py cancel-offer --help
Usage: nft.py cancel-offer [OPTIONS]

Options:
  --launcher-id TEXT     The ID of the NFT
  --offer-id TEXT        The ID of the offer you want to cancel
  --fingerprint INTEGER  The fingerprint of the key to use [optional]
  --help                 Show this message and exit.
```

Here is an example of canceling a buy offer.

```shell
$ python3 nft.py cancel-offer --offer-id 16 --launcher-id "356eb19da1fac4490c8f83e39788d5989cc0db5a2eaf8285a58cd7f4ebe07501"
Do you want to cancel your offer of 0.11 XCH for 'The fox'? [y/N]: y
You cancelled the offer.
```

## Showing your profile

The `profile` command can be used to show the singleton profile for a given wallet.
It requires a running wallet on your computer.

```shell
$ python3 nft.py profile --help
Usage: nft.py profile [OPTIONS]

Options:
  --fingerprint INTEGER  The fingerprint of the key to use [optional]
  --help                 Show this message and exit.
```

Here is an example.

```shell
$ python3 nft.py profile
Choose wallet key:
1) 1105740000
2) 2244950000
Enter a number to pick or q to quit: 1
Your singleton profile is https://xch.gallery/profile/991053e52414463d68cb9f8901f1bf1d7301acf2d1203b4fb28e2ea93c48f10b336a56077ac4fd9a591ce514e72beb00
```


## Updating your profile

The `update-profile` command can be used to show the singleton profile for a given wallet.
It requires a running wallet on your computer.

```shell
python3 nft.py update-profile --help
Usage: nft.py update-profile [OPTIONS]

Options:
  --name TEXT            Your profile name
  --fingerprint INTEGER  The fingerprint of the key to use
  --help                 Show this message and exit.
```

Here is an example.

```shell
$ python3 nft.py update-profile
Name: Acevail
Do you want to set your profile name to Acevail? [y/N]: y
Your profile has been updated!
You can inspect it using the following link: https://xch.gallery/profile/b3035d8ca2d572dec7843cc134277eec13e56c84afb2bd41ba78cb5a1b080033177433cfa8973bb5bd583ff55e96f4b4
```

## Attribution

The puzzles in this repository build on puzzles included in the [chia-blockchain](https://github.com/Chia-Network/chia-blockchain) project, which is licensed under Apache 2.0.
