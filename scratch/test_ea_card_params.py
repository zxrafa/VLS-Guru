import requests
import hashlib
import sys

# Configure standard output to use utf-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.ea.com/'
}

# Messi base card URL (Gold Raro)
base_url = "https://ratings-images-prod.pulse.ea.com/FC25/full/player-shields/pt-br/158023.png?width=265"

r_base = requests.get(base_url, headers=headers)
base_len = len(r_base.content)
base_hash = hashlib.md5(r_base.content).hexdigest()
print(f"Base Card (No parameters): Length={base_len} bytes, Hash={base_hash}")

# List of parameter configurations to test
params_to_test = [
    {"rarity": 3},        # TOTW
    {"rarityId": 3},
    {"shield": 3},
    {"shieldId": 3},
    {"background": 3},
    {"bg": 3},
    {"event": 3},
    {"collection": 3},
    {"rarity": 12},       # Icon
    {"rarityId": 12},
    {"shield": 12},
    {"shieldId": 12},
]

for p in params_to_test:
    name = list(p.keys())[0]
    val = p[name]
    test_url = f"{base_url}&{name}={val}"
    r_test = requests.get(test_url, headers=headers)
    test_len = len(r_test.content)
    test_hash = hashlib.md5(r_test.content).hexdigest()
    
    if test_hash != base_hash:
        print(f"DIFFERENT! Parameter {name}={val} changed the image! Length={test_len} bytes, Hash={test_hash}")
    else:
        print(f"Same image for parameter {name}={val}")
