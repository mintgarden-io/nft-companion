# singleton-utils

## Installation

1. Clone the repository
```shell
git clone https://github.com/xch-gallery/singleton-utils.git
cd singleton-utils
```

2. Run the install script and activate the virtual environment
```shell
./install.sh

. ./venv/bin/activate
```

## Sign a puzzle hash

The `sign` command can be used to sign a delegated puzzle hash for a standard coin spend.
It requires the following parameters:

```shell
$ ./main.py sign --help
Usage: main.py sign [OPTIONS]

Options:
  --delegated         Sign using synthetic key (needed for delegated puzzle
                      hashes)
                        
  --puzzle_hash TEXT  The puzzle hash to be signed
  --coin_id TEXT      The id of the coin to be spent
  --secret_key TEXT   The secret key to be used for signing
  --help              Show this message and exit.

```

The following example shows the signing of a delegated puzzle hash.

```shell
$ ./main.py sign --delegated --puzzle_hash 3ad325cde4343318e30368d9e765c016cb3c64449be207f299f040a35b484c9a --coin_id 55fc1ac0fcd8490483ac9fb43fddf37c73a02ca693bb7478a4170950ba0fe819
Secret key: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXx
signature: 8c112c15b8dc8e6a5e99c3c0f053b0cf89f503bc704d60153b94ef97980402dd859f163ad3415ec28a0daab938aea4390a9d66c46cc3b2b4d9dbe803c97a4cf6d59fa6110c3bfc85bbf3ea9bf86f85d3143c89207ee70fb6c18264611ecd2f1c


```