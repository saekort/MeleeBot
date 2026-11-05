import os
import sqlite3
import time
from datetime import datetime, timezone

import httpx

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
DB_PATH = "seen.db"
BASE = "https://melee.gg"

# Store name -> organization hub ID (the number in /Hub/Organization/<id>)
STORES = {
    "Animerch": 19603,
    "Arcane Forge": 20373,
    "De Tafelridder": 9276,
    "Friends & Foes": 4783,
    "ITSMAXTOYS": 20306,
    "Kai of Cards": 4459,
    "Labyrinth": 19493,
    "Livingstone Coffee": 20151,
    "Made-up Rules": 19253,
    "Playourgames Uden": 7828,
    "Side7": 8126,
    "Spelkwartier": 4109
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0",
    "Accept-Language": "en-US,en;q=0.9",
}

GAME = "CyberpunkTCG"

def fetch_tournaments(hub_id: int) -> list[dict]:
    found = {}
    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True,
                      cookies={"CookieConsent": "true"}) as client:
        client.get(f"{BASE}/")
        client.get(f"{BASE}/Hub/Organization/{hub_id}")

        start = 0
        while True:
            r = client.post(
                f"{BASE}/Hub/SearchOrganizationTournaments/{hub_id}",
                data={"draw": 1, "start": start, "length": 50},
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Origin": BASE,
                    "Referer": f"{BASE}/Hub/Organization/{hub_id}",
                },
            )
            if r.status_code != 200:
                print(f"  hub {hub_id}: HTTP {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
            payload = r.json()

            rows = payload.get("data", [])
            for t in rows:
                if t.get("Game") != GAME:
                    continue
                if t.get("StatusDescription") == "Ended":
                    continue
                found[t["ID"]] = {
                    "id": str(t["ID"]),
                    "name": t["Name"],
                    "start": datetime.fromisoformat(t["StartDate"].replace("Z", "+00:00")),
                    "players": t.get("ParticipatingCount"),
                    "cap": t.get("PlayerCap"),
                    "entry": t.get("EntryFeeString") or t.get("EntryTypeDescription"),
                    "url": f"{BASE}/Tournament/View/{t['ID']}",
                }

            start += len(rows)
            if not rows or start >= payload.get("recordsFiltered", 0):
                break
    return list(found.values())

def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS seen (hub_id INTEGER, tournament_id TEXT, "
        "PRIMARY KEY (hub_id, tournament_id))"
    )
    # Upgrade older databases by adding any missing columns
    existing = {row[1] for row in conn.execute("PRAGMA table_info(seen)")}
    for col, col_type in (("name", "TEXT"), ("start", "TEXT"), ("url", "TEXT"),
                          ("players", "INTEGER"), ("cap", "INTEGER"),
                          ("entry", "TEXT")):
        if col not in existing:
            conn.execute(f"ALTER TABLE seen ADD COLUMN {col} {col_type}")
    conn.commit()
    conn.execute("CREATE TABLE IF NOT EXISTS seeded (hub_id INTEGER PRIMARY KEY)")
    conn.execute("INSERT OR IGNORE INTO seeded SELECT DISTINCT hub_id FROM seen")
    conn.commit()
    return conn

def post_to_discord(store_name: str, t: dict) -> None:
    ts = int(t["start"].timestamp())
    fields = [{"name": "Starts", "value": f"<t:{ts}:F> (<t:{ts}:R>)"}]
    if t["cap"]:
        fields.append({"name": "Players", "value": f"{t['players']}/{t['cap']}", "inline": True})
    if t["entry"]:
        fields.append({"name": "Entry fee", "value": t["entry"], "inline": True})
    embed = {
        "title": t["name"],
        "url": t["url"],
        "description": f"New tournament from **{store_name}**",
        "fields": fields,
    }
    r = httpx.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
    r.raise_for_status()
    time.sleep(1)

def announce_store(store_name: str) -> None:
    if store_name not in STORES:
        print(f"Unknown store '{store_name}'. Known stores: {', '.join(STORES)}")
        return

    tournaments = sorted(fetch_tournaments(STORES[store_name]), key=lambda x: x["start"])

    lines = []
    for t in tournaments:
        ts = int(t["start"].timestamp())
        label = t["name"] or f"Tournament {t['id']}"
        link = f"[{label}]({t['url']})" if t["url"] else label
        details = []
        if t["players"] is not None and t["cap"]:
            details.append(f"{t['players']}/{t['cap']}")
        if t["entry"]:
            details.append(t["entry"])
        extra = " · " + " · ".join(details) if details else ""
        lines.append(f"<t:{ts}:f> · {link}{extra}")

    if not lines:
        embeds = [{"title": store_name, "description": "No upcoming events"}]
    else:
        # An embed description holds at most 4096 characters, so split long lists
        chunks, current = [], ""
        for line in lines:
            if len(current) + len(line) + 1 > 4000:
                chunks.append(current)
                current = ""
            current += line + "\n"
        chunks.append(current)
        embeds = [
            {"title": store_name if i == 0 else f"{store_name} (cont.)", "description": chunk}
            for i, chunk in enumerate(chunks)
        ]

    for embed in embeds:
        r = httpx.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        r.raise_for_status()
        time.sleep(1)
    print(f"Posted {len(embeds)} message(s) for {store_name}.")

def post_all_to_discord(upcoming_only: bool = False) -> None:
    conn = init_db()
    now = datetime.now(timezone.utc)
    embeds = []

    for store_name, hub_id in STORES.items():
        rows = conn.execute(
            "SELECT tournament_id, name, start, url, players, cap, entry FROM seen "
            "WHERE hub_id = ? AND start IS NOT NULL ORDER BY start",
            (hub_id,),
        ).fetchall()

        lines = []
        for tid, name, start, url, players, cap, entry in rows:
            dt = datetime.fromisoformat(start)
            if upcoming_only and dt < now:
                continue
            ts = int(dt.timestamp())
            label = name or f"Tournament {tid}"
            link = f"[{label}]({url})" if url else label
            details = []
            if players is not None and cap:
                details.append(f"{players}/{cap}")
            if entry:
                details.append(entry)
            extra = " · " + " · ".join(details) if details else ""
            lines.append(f"<t:{ts}:f> · {link}{extra}")

        if not lines:
            embeds.append({"title": store_name, "description": "No upcoming events"})
            continue

        # An embed description holds at most 4096 characters, so split long lists
        chunks, current = [], ""
        for line in lines:
            if len(current) + len(line) + 1 > 4000:
                chunks.append(current)
                current = ""
            current += line + "\n"
        chunks.append(current)

        for i, chunk in enumerate(chunks):
            title = store_name if i == 0 else f"{store_name} (cont.)"
            embeds.append({"title": title, "description": chunk})

    for embed in embeds:
        r = httpx.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        r.raise_for_status()
        time.sleep(1)  # stay well within webhook rate limits
    print(f"Posted {len(embeds)} message(s).")

# DEV functions
def show_db() -> None:
    conn = init_db()

    for store_name, hub_id in STORES.items():
        rows = conn.execute(
            "SELECT tournament_id, name, start, players, cap, entry FROM seen "
            "WHERE hub_id = ? ORDER BY start",
            (hub_id,),
        ).fetchall()

        print(f"{store_name}  [hub {hub_id}]")
        print("-" * 80)
        if not rows:
            print("  (no tournaments stored)\n")
            continue

        for tid, name, start, players, cap, entry in rows:
            when = start[:16].replace("T", " ") + " UTC" if start else "unknown date"
            if players is None:
                slots = "?"
            elif cap:
                slots = f"{players}/{cap}"
            else:
                slots = f"{players}/-"
            fee = entry or "?"
            print(f"  {when}  {slots:>6}  {fee:<8}  #{tid:<8} {name or '(name not stored yet)'}")
        print(f"  ({len(rows)} tournaments)\n")

    # Stores that are in the database but no longer in STORES
    known = tuple(STORES.values())
    placeholders = ",".join("?" * len(known))
    orphans = conn.execute(
        f"SELECT DISTINCT hub_id FROM seen WHERE hub_id NOT IN ({placeholders})",
        known,
    ).fetchall()
    for (hub_id,) in orphans:
        print(f"Removed store [hub {hub_id}] still has rows in the database")

def remove_tournament(tournament_id: str) -> None:
    conn = init_db()
    row = conn.execute(
        "SELECT name FROM seen WHERE tournament_id = ?", (tournament_id,)
    ).fetchone()
    if not row:
        print(f"No tournament with ID {tournament_id} in the database.")
        return
    conn.execute("DELETE FROM seen WHERE tournament_id = ?", (tournament_id,))
    conn.commit()
    print(f"Removed #{tournament_id}: {row[0] or '(name not stored)'}")

# MAIN
def main() -> None:
    conn = init_db()
    for store_name, hub_id in STORES.items():
        try:
            tournaments = fetch_tournaments(hub_id)
        except Exception as e:
            print(f"[{store_name}] fetch failed: {e}")
            continue
        print(f"[{store_name}] fetched {len(tournaments)} tournaments")

        # Seed silently the first time a store is fetched, so adding a store doesn't spam
        first_time = conn.execute(
            "SELECT 1 FROM seeded WHERE hub_id = ?", (hub_id,)
        ).fetchone() is None

        for t in tournaments:
            seen = conn.execute(
                "SELECT 1 FROM seen WHERE hub_id = ? AND tournament_id = ?",
                (hub_id, t["id"]),
            ).fetchone()
            if seen:
                conn.execute(
                    "UPDATE seen SET name = ?, start = ?, url = ?, players = ?, cap = ?, entry = ? "
                    "WHERE hub_id = ? AND tournament_id = ?",
                    (t["name"], t["start"].isoformat(), t["url"],
                     t["players"], t["cap"], t["entry"], hub_id, t["id"]),
                )
                conn.commit()
                continue
            if not first_time:
                try:
                    post_to_discord(store_name, t)
                except Exception as e:
                    print(f"[{store_name}] post failed for #{t['id']}: {e}")
                    continue  # not saved, so it is retried on the next run
            conn.execute(
                "INSERT INTO seen (hub_id, tournament_id, name, start, url, players, cap, entry) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (hub_id, t["id"], t["name"], t["start"].isoformat(), t["url"],
                 t["players"], t["cap"], t["entry"]),
            )
            conn.commit()

        conn.execute("INSERT OR IGNORE INTO seeded (hub_id) VALUES (?)", (hub_id,))
        conn.commit()
        time.sleep(2)  # be polite to Melee between stores

if __name__ == "__main__":
    import sys
    if "--show" in sys.argv:
        show_db()
    elif "--post-all" in sys.argv:
        post_all_to_discord()
    elif "--post-upcoming" in sys.argv:
        post_all_to_discord(upcoming_only=True)
    elif "--announce" in sys.argv:
        i = sys.argv.index("--announce")
        if i + 1 >= len(sys.argv):
            print('Usage: python announcer.py --announce "Made-up Rules"')
        else:
            announce_store(sys.argv[i + 1])
    elif "--remove" in sys.argv:
        i = sys.argv.index("--remove")
        if i + 1 >= len(sys.argv):
            print("Usage: python announcer.py --remove <tournament_id>")
        else:
            remove_tournament(sys.argv[i + 1])
    else:
        main()