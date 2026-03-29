import streamlit as st
import pandas as pd

from utils import player_img_url


def render(all_stats, w, l):
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

    # ── Analytics Feature Suggestions ────────────────────────────────────────
    st.divider()
    with st.expander("💡 Potential Analytics Features (Coming Soon?)"):
        st.markdown("""
These are features that could make the sim richer — let us know which you'd like to see:

**1. 🕸️ Player Performance Radar**
Spider chart (PTS / REB / AST / STL / BLK) for your starters vs. the opponent's top 5 — shown in the Gameplan tab before each game.

**2. 💰 Salary vs. Performance Scatter**
Bubble chart of your roster: X = salary, Y = overall rating, bubble size = PPG. Instantly spot overpaid players and trade targets.

**3. 📅 Opponent Strength Schedule**
Bar chart of remaining opponents sorted by OVR rating, color-coded easy/tough. Plan when to rest stars.

**4. 🌡️ Stamina Heatmap** *(Hard Mode)*
Grid of players × games showing end-of-game stamina across the season. Visualize who needs rest before injury strikes.

**5. 🎲 Playoff Series Win Probability**
Before each playoff game, show a gauge chart with simulated win probability based on OVR differential, stamina, and home/away.

**6. 📊 Season Leader Boards**
Full league-wide stat leaders (PTS, REB, AST leaders across all 30 teams), not just your roster.
""")
