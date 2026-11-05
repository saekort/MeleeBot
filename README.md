# MeleeBot

A small Python script that watches the public organizer pages of selected stores on [melee.gg](https://melee.gg) and posts to a Discord channel (through a webhook) whenever a store lists a **new Cyberpunk TCG tournament**.

Each announcement shows the tournament name (linked to its Melee page), start time (shown in every viewer's own time zone), player count and entry fee. The script remembers what it has already announced in a local SQLite file, so every tournament is announced only once.

> **Not affiliated with Melee.** This tool only reads the public tournament lists that Melee's organizer hub pages already show to every visitor. It makes a handful of requests per run, so please keep the schedule modest (every 15 to 30 minutes is plenty) and respect Melee's terms of service. The author contacted Melee about this use before publishing it.

## Requirements

- Python 3.9 or newer
- A Discord webhook URL (see below)

## Installation

```bash
git clone https://github.com/saekort/meleebot.git
cd meleebot
python -m venv venv
```

Activate the virtual environment:

| Shell | Command |
|---|---|
| Git Bash (Windows) | `source venv/Scripts/activate` |
| PowerShell (Windows) | `venv\Scripts\Activate.ps1` |
| Command Prompt (Windows) | `venv\Scripts\activate` |
| Linux / macOS | `source venv/bin/activate` |

Then install the dependencies:

```bash
pip install -r requirements.txt
```

You need to activate the virtual environment again each time you open a new terminal. You only create it once.

## Setting up the Discord webhook

1. In Discord, open your server: **channel settings → Integrations → Webhooks → New Webhook**, choose the channel, and copy the webhook URL.
2. Give the URL to the script through the `DISCORD_WEBHOOK_URL` environment variable.

| Shell | Command |
|---|---|
| Git Bash / Linux / macOS | `export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."` |
| PowerShell | `$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."` |
| Windows, permanent (open a new terminal afterwards) | `setx DISCORD_WEBHOOK_URL "https://discord.com/api/webhooks/..."` |

`export` and `$env:` only last for the current terminal window. On Linux and macOS you can add the `export` line to `~/.bashrc` (or your shell's equivalent) to make it permanent.

**Treat the webhook URL as a secret.** Anyone who has it can post to your channel. Never commit it to the repository. If it ever leaks, delete the webhook in Discord and create a new one.

The script reads the variable as soon as it starts, so it must be set for **every** command below, including the read-only ones.

## Configuration

Both settings are near the top of `announcer.py`.

**Stores.** Add each store to the `STORES` dictionary as `"Display name": organizer_id`:

```python
STORES = {
    "Made-up Rules": 19253,
    "Kai of Cards": 4459,
}
```

To find a store's ID, open its organizer hub page on Melee. The number in the address `https://melee.gg/Hub/Organization/<id>` is the ID you need. Use the **organizer** ID, not the venue ID: addresses that look like `/Hub/Location/<id>` are venue pages, and their numbers do not work. A store with the wrong ID simply shows no events.

**Game.** `GAME = "CyberpunkTCG"` limits the bot to one game. Tournaments for other games are ignored and never stored. To track a different game, change this to Melee's internal name for it.

## Usage

Run the bot (this is what you schedule):

```bash
python announcer.py
```

For every store it fetches the upcoming tournaments, announces the ones it hasn't seen before, and stores them in `seen.db`.

**The first run for a store is silent.** Tournaments that already exist when a store is first fetched are saved without announcing them, so adding a store never floods your channel. From then on, new tournaments are announced as they appear.

## Command-line options

Run `python announcer.py` with one of these flags. Without a flag, it does the normal fetch-and-announce run described above.

| Option | What it does | Contacts Melee? | Posts to Discord? |
|---|---|---|---|
| *(none)* | Normal run: fetch all stores, announce new tournaments, update the database | Yes | Only for new tournaments |
| `--show` | Prints everything in the database, grouped per store, with date, players, entry fee and ID | No | No |
| `--post-all` | Posts an overview of everything in the database to Discord, one message per store | No | Yes |
| `--post-upcoming` | Same overview, but only tournaments that haven't started yet. Stores with nothing upcoming show "No upcoming events" | No | Yes |
| `--announce "<store>"` | Fetches one store live and posts its upcoming tournaments as a single overview message | Yes | Yes |
| `--remove <tournament_id>` | Deletes one tournament from the database | No | No |

Examples:

```bash
python announcer.py --show
python announcer.py --post-upcoming
python announcer.py --announce "Made-up Rules"
python announcer.py --remove 492390
```

Notes:

- `--post-all`, `--post-upcoming` and `--show` use what the last normal run saved, so run `python announcer.py` first if you want fresh player counts.
- `--announce` uses the exact store name from `STORES`, in quotes.
- `--remove` is useful for testing: delete a tournament, then run the normal command, and the bot announces it again as if it were new. Tournament IDs are the numbers after `#` in the `--show` output. Note that a tournament that is still listed on Melee will be announced again after you remove it.
- None of the manual commands change what the normal run considers "already announced", except `--remove`.

## Running it automatically

Schedule the normal run (no flags) every 15 to 30 minutes.

**Linux / macOS (cron):**

```cron
*/15 * * * * cd /path/to/meleebot && DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..." ./venv/bin/python announcer.py
```

**Windows (Task Scheduler):** create a task that repeats every 15 minutes with:

- Program: `C:\path\to\meleebot\venv\Scripts\python.exe`
- Arguments: `announcer.py`
- Start in: `C:\path\to\meleebot`

Set `DISCORD_WEBHOOK_URL` as a permanent user environment variable (`setx`, see above) so the task can see it.

Using the virtual environment's own Python as shown means you don't have to activate anything.

## How it works

1. For each store, the script requests the same list Melee's own hub page loads, filtered to the configured game and skipping tournaments that have already ended.
2. It compares each tournament ID with `seen.db`.
3. New tournaments are posted to Discord as an embed and then saved. If posting fails, the tournament is not saved, so it is retried on the next run.
4. Already known tournaments get their details (name, start time, player count, fee) refreshed in the database.

`seen.db` is a SQLite file created next to the script. It is safe to delete: the next run saves everything it finds silently and announces nothing, then continues normally.

## Troubleshooting

- **`KeyError: 'DISCORD_WEBHOOK_URL'`:** the environment variable isn't set in this terminal. See the webhook section.
- **`ModuleNotFoundError: No module named 'httpx'`:** the virtual environment isn't active, or the dependencies aren't installed.
- **A store shows no tournaments:** check that you used its organizer ID (see Configuration), and that it actually has an upcoming tournament for the configured game.
- **`fetch failed ... 403` or another HTTP error:** Melee refused or changed the request. The script keeps going with the other stores. This is an unofficial endpoint that could change at any time, so if it keeps failing, open an issue.
- **Nothing gets announced after adding a store:** the first fetch of a store is silent by design.

## License

See the [LICENSE](LICENSE) file.