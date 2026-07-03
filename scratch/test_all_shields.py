import requests
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.ea.com/'
}

shield_ids = [1, 3, 12, 21, 45]

patterns = [
    "https://ratings-images-prod.pulse.ea.com/FC25/full/shields/web/p/{}.png",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/shields/web/p{}.png",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/shields/p{}.png",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/player-shields/shields/{}.png",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/player-shields/p/{}.png",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/player-shields/pt-br/shields/{}.png",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/player-shields/pt-br/p/{}.png",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/player-shields/pt-br/p{}.png",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/player-shields/web/p/{}.png",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/shields/p/{}.png?width=265",
    "https://ratings-images-prod.pulse.ea.com/FC25/full/shields/{}.png?width=265"
]

for pat in patterns:
    print(f"Testing pattern: {pat}")
    for sid in shield_ids:
        url = pat.format(sid)
        try:
            r = requests.head(url, headers=headers, timeout=2)
            if r.status_code == 200:
                print(f"  [FOUND] ID {sid}: HTTP 200!")
            else:
                print(f"  ID {sid}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  ID {sid}: Error: {e}")
