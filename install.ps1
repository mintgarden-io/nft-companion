git clone https://github.com/xch-gallery/nft-companion
cd nft-companion
python -m venv venv
./venv/Scripts/activate
python -m pip install --upgrade pip

pip3 install wheel 
pip3 install .
pip3 install chia-dev-tools --no-deps
