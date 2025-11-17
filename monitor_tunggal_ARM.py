# monitor_multi.py
# Monitor 2 Place Roblox + header ASCII "tetap di atas" + Discord Embed rapi

import os, csv, time, requests
from datetime import datetime, timedelta
from collections import deque

# ======================= CONFIG =======================
# Isi 2 (atau lebih) place di sini: {place_id: "Nama Tampilan"}
PLACE_MAP = {
    73429689663522: "MOUNT TUNGGAL",   # yang lama
    136142993541285:      "MOUNT ARM" # yang baru
}

INTERVAL_SEC = 60                         # jeda cek (detik)
CSV_PATH = "roblox_monitor_multi.csv"     # file log CSV gabungan
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1437172017412706344/vhR_QC3mEJxdaNdjGljrV0EgfguyduB3But5Fq7cRygTIrGFy6a5a61LPgdBv-YzCPIv"
SEND_MIN_INTERVAL_MIN = 10                # anti spam interval
# ======================================================

RECENT_MAX = 6
recent_lines = deque(maxlen=RECENT_MAX)

ASCII_HEADER = r"""
 ________                                                  __         ___             ______   _______   __       __ 
/        |                                                /  |       /   \           /      \ /       \ /  \     /  |
$$$$$$$$/__    __  _______    ______    ______    ______  $$ |      /$$$  |         /$$$$$$  |$$$$$$$  |$$  \   /$$ |
   $$ | /  |  /  |/       \  /      \  /      \  /      \ $$ |      $$ $$ \__       $$ |__$$ |$$ |__$$ |$$$  \ /$$$ |
   $$ | $$ |  $$ |$$$$$$$  |/$$$$$$  |/$$$$$$  | $$$$$$  |$$ |      /$$$     |      $$    $$ |$$    $$< $$$$  /$$$$ |
   $$ | $$ |  $$ |$$ |  $$ |$$ |  $$ |$$ |  $$ | /    $$ |$$ |      $$ $$ $$/       $$$$$$$$ |$$$$$$$  |$$ $$ $$/$$ |
   $$ | $$ \__$$ |$$ |  $$ |$$ \__$$ |$$ \__$$ |/$$$$$$$ |$$ |      $$ \$$  \       $$ |  $$ |$$ |  $$ |$$ |$$$/ $$ |
   $$ | $$    $$/ $$ |  $$ |$$    $$ |$$    $$ |$$    $$ |$$ |      $$   $$  |      $$ |  $$ |$$ |  $$ |$$ | $/  $$ |
   $$/   $$$$$$/  $$/   $$/  $$$$$$$ | $$$$$$$ | $$$$$$$/ $$/        $$$$/$$/       $$/   $$/ $$/   $$/ $$/      $$/ 
                            /  \__$$ |/  \__$$ |                                                                     
                            $$    $$/ $$    $$/                                                                      
                             $$$$$$/   $$$$$$/                                                                                   
"""

def fetch_total_players(place_id: int) -> tuple[int, int]:
    total_players = 0
    total_servers = 0
    cursor = None
    while True:
        url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?sortOrder=Asc&limit=100"
        if cursor:
            url += f"&cursor={cursor}"
        r = requests.get(url, timeout=15)
        if r.status_code == 429:          # rate limited
            time.sleep(60)
            continue
        r.raise_for_status()
        js = r.json()
        servers = js.get("data", [])
        total_servers += len(servers)
        total_players += sum(s.get("playing", 0) for s in servers)
        cursor = js.get("nextPageCursor")
        if not cursor:
            break
    return total_players, total_servers

def clear_and_home():
    print("\033[2J\033[H", end="")

def render_screen(status_line: str, rows: list[tuple[int, str, int, int]]):
    clear_and_home()
    print(ASCII_HEADER)
    print(f"Interval: {INTERVAL_SEC}s  |  CSV: {CSV_PATH}")
    print("-" * 80)
    print(status_line)
    print("-" * 80)

    # TANPA PLACE ID
    print(f"{'Nama':<25} {'Online':>8} {'Servers':>8}")
    print("-" * 80)
    for pid, name, pl, sv in rows:
        print(f"{name:<25} {pl:>8} {sv:>8}")

    print("-" * 80)
    print("Recent:")
    for ln in list(recent_lines)[-RECENT_MAX:]:
        print(ln)
    print("-" * 80)
    print("Tips: Ctrl+C buat stop.")

def append_csv(ts: str, place_id: int, name: str, players: int, servers: int):
    new_file = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["timestamp", "place_id", "name", "players", "servers"])
        w.writerow([ts, place_id, name, players, servers])

def send_discord_embed(snapshot: dict[int, tuple[int,int]]):
    """snapshot = {place_id: (players, servers)}"""
    if not DISCORD_WEBHOOK:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # bikin satu embed, field per map, rapi
    fields = []
    total_p = total_s = 0
    for pid, (players, servers) in snapshot.items():
        name = PLACE_MAP.get(pid, str(pid))
        url = f"https://www.roblox.com/games/{pid}"
        fields.append({
            "name": f"{name}",
            "value": f"[Link]({url}) • **Online:** `{players:,}` • **Servers:** `{servers:,}` • `PlaceID: {pid}`",
            "inline": False
        })
        total_p += players
        total_s += servers

    payload = {
        "embeds": [{
            "title": "Live Monitor — Multi Place",
            "description": f"Total Online: **{total_p:,}** • Total Servers: **{total_s:,}**",
            "color": 0x21A366,
            "fields": fields,
            "footer": {"text": f"Update: {ts} (UTC+7)"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
    except Exception:
        pass

def main():
    # state per-place buat anti-spam
    last_stats: dict[int, tuple[int,int]] = {}  # pid -> (players, servers)
    last_sent_at: datetime | None = None

    status = "Init… nunggu fetch pertama."
    render_screen(status, [])

    while True:
        snapshot = {}
        rows_for_screen = []
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            # ambil data semua place
            for pid, name in PLACE_MAP.items():
                players, servers = fetch_total_players(pid)
                snapshot[pid] = (players, servers)
                rows_for_screen.append((pid, name, players, servers))
                append_csv(ts, pid, name, players, servers)

            # recent line ringkas
            line = f"[{ts}] " + " | ".join(
                f"{PLACE_MAP[pid]}: {pl} online/{sv} srv" for pid, (pl, sv) in snapshot.items()
            )
            recent_lines.append(line)

            # tentukan apakah kirim discord (berubah atau lewat interval)
            changed = any(snapshot.get(pid) != last_stats.get(pid) for pid in PLACE_MAP.keys())
            due = (last_sent_at is None) or (datetime.now() - last_sent_at >= timedelta(minutes=SEND_MIN_INTERVAL_MIN))
            if changed or due:
                send_discord_embed(snapshot)
                last_sent_at = datetime.now()
                last_stats = snapshot.copy()

            status = f"UPDATE TERAKHIR: {ts} — OK"
        except Exception as e:
            err = f"[{ts}] Error: {e}"
            recent_lines.append(err)
            status = f"ERROR, retry bentar… {e}"

        render_screen(status, rows_for_screen)
        time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    main()
