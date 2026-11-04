import httpx

BASE = "https://melee.gg"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0",
    "Accept-Language": "en-US,en;q=0.9",
}
STORES = {"Animerch": 19603, "Arcane Forge": 20373, "De Tafelridder": 9276}  # put your real IDs here


def fetch(hub_id, extra_cookies):
    cookies = {"CookieConsent": "true", **extra_cookies}
    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True, cookies=cookies) as c:
        c.get(f"{BASE}/")
        c.get(f"{BASE}/Hub/Organization/{hub_id}")
        r = c.post(
            f"{BASE}/Hub/OrganizationTournaments/{hub_id}",
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "*/*",
                     "Origin": BASE, "Referer": f"{BASE}/Hub/Organization/{hub_id}"},
        )
        r.raise_for_status()
        return {t["ID"]: t["Name"]
                for s in ("Featured", "Next")
                for t in r.json().get(s, {}).get("Tournaments", [])}


for name, hub_id in STORES.items():
    plain = fetch(hub_id, {})
    cyber = fetch(hub_id, {"selected-game": "CyberpunkTCG"})
    print(f"{name}: without cookie {len(plain)}, with cookie {len(cyber)}")
    for tid in plain.keys() - cyber.keys():
        print(f"   only without cookie: {plain[tid]}")