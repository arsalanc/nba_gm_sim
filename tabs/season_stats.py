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
