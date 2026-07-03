import requests
import json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.ea.com/'
}

url_api = "https://drop-api.ea.com/rating/ea-sports-fc"

for search_name in ["Messi", "Neymar"]:
    print(f"\nSearching for '{search_name}':")
    params = {"locale": "pt-br", "limit": 20, "search": search_name}
    r = requests.get(url_api, params=params, headers=headers)
    if r.status_code == 200:
        items = r.json().get("items", [])
        print(f"Found {len(items)} items:")
        for item in items:
            p_id = item.get("id")
            name = f"{item.get('firstName')} {item.get('lastName')} ({item.get('commonName')})"
            over = item.get("overallRating")
            avatar = item.get("avatarUrl")
            # Get rarity or shield info if any
            rank = item.get("rank")
            print(f"  - ID: {p_id} | Name: {name} | OVR: {over} | Rank: {rank}")
            print(f"    Avatar: {avatar}")
    else:
        print(f"Error {r.status_code}")
