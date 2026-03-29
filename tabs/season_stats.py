import streamlit as st
import pandas as pd

from utils import player_img_url, team_logo_url


def render(all_stats, w, l, all_teams):
    st.subheader("Season Statistics")
    st.write(f"**Games played:** {len(st.session_state.results)} | **Record:** {w}W — {l}L")

    if st.session_state.season_pts:
        df_leader = (
            pd.DataFrame(
                st.session_state.season_pts.items(),
                columns=['Player', 'Total Points']
            )
            .sort_values('Total Points', ascending=False)
            .merge(all_stats[['PLAYER', 'PLAYER_ID']], left_on='Player', right_on='PLAYER', how='left')
        )

        hdr = st.columns([1, 4, 2])
        hdr[1].write("**Player**")
        hdr[2].write("**Season Points**")
        st.divider()
        for _, row in df_leader.head(15).iterrows():
            rc = st.columns([1, 4, 2])
            if pd.notna(row.get('PLAYER_ID')):
                rc[0].image(player_img_url(int(row['PLAYER_ID'])), width=45)
            rc[1].write(f"**{row['Player']}**")
            rc[2].write(f"{int(row['Total Points'])} pts")
    else:
        st.info("Play some games to see season stats here.")

    # ── Win % Trend ───────────────────────────────────────────────────────────
    results = st.session_state.results
    if len(results) >= 5:
        st.divider()
        st.subheader("📈 Win % Trend")
        win_pct = []
        for i in range(1, len(results) + 1):
            wins = results[:i].count('W')
            win_pct.append(round(wins / i, 3))
        st.line_chart(win_pct)
        st.caption("Rolling win percentage over the season.")

    # ── League Leader Boards ──────────────────────────────────────────────────
    st.divider()
    st.subheader("📊 League Leader Boards")

    team_abbr_map = {t['id']: t['abbreviation'] for t in all_teams}

    def _leader_table(stat_col, label, n=10):
        top = (
            all_stats[['PLAYER', 'PLAYER_ID', 'TEAM_ID', stat_col]]
            .dropna(subset=[stat_col])
            .sort_values(stat_col, ascending=False)
            .head(n)
            .reset_index(drop=True)
        )
        hdr = st.columns([1, 1, 4, 2, 2])
        hdr[0].write("**#**")
        hdr[1].write("")
        hdr[2].write("**Player**")
        hdr[3].write("**Team**")
        hdr[4].write(f"**{label}**")
        st.divider()
        for rank, row in top.iterrows():
            rc = st.columns([1, 1, 4, 2, 2])
            rc[0].write(f"{rank + 1}")
            pid = int(row['PLAYER_ID'])
            if pid:
                rc[1].image(player_img_url(pid), width=35)
            rc[2].write(row['PLAYER'])
            tid = int(row['TEAM_ID'])
            abbr = team_abbr_map.get(tid, '?')
            logo_col, abbr_col = rc[3].columns([1, 2])
            logo_col.image(team_logo_url(tid), width=25)
            abbr_col.write(abbr)
            rc[4].write(f"**{row[stat_col]:.1f}**")

    lb_pts, lb_reb, lb_ast = st.tabs(["🏀 Points", "💪 Rebounds", "🎯 Assists"])
    with lb_pts:
        _leader_table('PTS', 'PPG')
    with lb_reb:
        _leader_table('REB', 'RPG')
    with lb_ast:
        _leader_table('AST', 'APG')

    # ── Analytics Feature Suggestions ────────────────────────────────────────
    st.divider()
    with st.expander("💡 Potential Analytics Features (Coming Soon?)"):
        st.markdown("""
These are features that could make the sim richer — let us know which you'd like to see:

**1. 🕸️ Player Performance Radar**
Spider chart (PTS / REB / AST / STL / BLK) for your starters vs. the opponent's top 5 — shown in the Gameplan tab before each game.

**2. 💰 Salary vs. Performance Scatter**
Bubble chart of your roster: X = salary, Y = overall rating, bubble size = PPG. Instantly spot overpaid players and trade targets.

**3. 🌡️ Stamina Heatmap** *(Hard Mode)*
Grid of players × games showing end-of-game stamina across the season. Visualize who needs rest before injury strikes.

**4. 🎲 Playoff Series Win Probability**
Before each playoff game, show a gauge chart with simulated win probability based on OVR differential, stamina, and home/away.

**5. 📅 Season Selection**
Choose which NBA season's roster and stats to pull (e.g. 2023-24, 2024-25, 2025-26). Play with your favorite era's rosters or compare different seasons.
""")
