"""Regenerate the bundled NBA data snapshot.

Run this locally (stats.nba.com blocks datacenter IPs, so it won't work from
cloud hosts) and commit the resulting nba_snapshot.csv. The deployed app falls
back to this file whenever the live API is unreachable.

    python make_snapshot.py
"""
from utils import fetch_live_nba_stats, SNAPSHOT_FILE

df = fetch_live_nba_stats(timeout=30)
df.to_csv(SNAPSHOT_FILE, index=False)
print(f"Wrote {len(df)} players ({df['TEAM_ID'].nunique()} teams) to {SNAPSHOT_FILE}")
