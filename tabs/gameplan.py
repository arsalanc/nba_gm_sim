import streamlit as st

from utils import player_img_url, team_logo_url, overall_badge
from engine import generate_round_matchups, find_user_matchup


def _render_player_card(col, player_row, injured_list=None):
    ovr = int(player_row['OVERALL'])
    name = player_row['PLAYER']
    pid = int(player_row['PLAYER_ID'])
    pos = player_row.get('POSITION', '?') or '?'
    is_injured = injured_list and name in injured_list

    img_c, info_c = col.columns([1, 3])
    img_c.image(player_img_url(pid), width=65)

    label = f"**{name}**"
    if is_injured:
        label += f"  🏥 OUT {injured_list[name]}g"
    info_c.markdown(label)
    info_c.write(f"`{pos}`  {overall_badge(ovr)}")

    stat_parts = [f"{player_row['PTS']:.1f} PPG"]
    if 'REB' in player_row:
        stat_parts.append(f"{player_row['REB']:.1f} REB")
    if 'AST' in player_row:
        stat_parts.append(f"{player_row['AST']:.1f} AST")
    info_c.caption(" · ".join(stat_parts))


def render(my_team, current_team_id, roster, all_teams, all_stats, season_phase, games_played, season_length=82):
    next_opp_id = None

    if season_phase == 'playoffs_user' and st.session_state.current_series:
        next_opp_id = st.session_state.current_series['opponent_id']
        series_info = st.session_state.current_series
        round_labels = {'round1': 'First Round', 'round2': 'Semifinals',
                        'conf_finals': 'Conference Finals', 'finals': 'NBA Finals'}
        st.markdown(f"### 🏆 {round_labels.get(series_info['round'], 'Playoffs')}")
        st.write(f"Series: **{my_team['abbreviation']} {series_info['user_wins']}** — "
                 f"**{series_info['opp_wins']}** "
                 f"{next((t for t in all_teams if t['id'] == next_opp_id), {}).get('abbreviation', '?')}")
    elif season_phase in ('playoffs_spectate', 'offseason'):
        st.info("Your season is over. Check the **Standings** tab for playoff results.")
    elif games_played >= season_length:
        st.info("Regular season is over! Check the **Standings** tab for playoff picture.")
    else:
        matchups_preview = generate_round_matchups(all_teams, games_played)
        next_opp_id, _ = find_user_matchup(matchups_preview, current_team_id)

    if next_opp_id is None and season_phase == 'regular' and games_played < season_length:
        st.info("No upcoming opponent yet.")
    else:
        opp_team_info = next((t for t in all_teams if t['id'] == next_opp_id), None)
        if opp_team_info is None:
            st.warning("Could not load opponent info.")
        else:
            opp_roster_full = all_stats[all_stats['TEAM_ID'] == next_opp_id].copy()
            opp_starters = opp_roster_full.nlargest(5, 'OVERALL')

            saved_starters = st.session_state.get('current_starters', [])
            if len(saved_starters) == 5:
                my_lineup_df = roster[roster['PLAYER'].isin(saved_starters)]
                my_avg_ovr = int(my_lineup_df['OVERALL'].mean())
            else:
                my_lineup_df = roster.nlargest(5, 'OVERALL')
                my_avg_ovr = int(my_lineup_df['OVERALL'].mean())
            opp_avg_ovr = int(opp_starters['OVERALL'].mean())

            # ── Header ───────────────────────────────────────────────────
            hdr_my, hdr_vs, hdr_opp = st.columns([2, 1, 2])
            with hdr_my:
                lc, nc = st.columns([1, 2])
                lc.image(team_logo_url(current_team_id), width=90)
                nc.subheader(my_team['full_name'])
                nc.caption(f"OVR {my_avg_ovr}")
            hdr_vs.markdown(
                "<div style='text-align:center;padding-top:20px;font-size:1.4rem;font-weight:bold'>VS</div>",
                unsafe_allow_html=True,
            )
            with hdr_opp:
                lc, nc = st.columns([1, 2])
                lc.image(team_logo_url(next_opp_id), width=90)
                nc.subheader(opp_team_info['full_name'])
                nc.caption(f"OVR {opp_avg_ovr}")

            # Team strength bar
            st.caption("Team strength — avg OVERALL of top 5")
            my_share = my_avg_ovr / (my_avg_ovr + opp_avg_ovr)
            st.progress(my_share)
            st.caption(f"{'Favored ✅' if my_avg_ovr >= opp_avg_ovr else 'Underdog ⚠️'} ({my_avg_ovr} vs {opp_avg_ovr})")

            st.divider()

            # ── Side-by-side rosters ──────────────────────────────────────
            col_yours, col_theirs = st.columns(2)

            with col_yours:
                lc, nc = st.columns([1, 4])
                lc.image(team_logo_url(current_team_id), width=50)
                if len(saved_starters) == 5:
                    nc.subheader(f"Projected Lineup — {my_team['abbreviation']}")
                    display_df = roster[roster['PLAYER'].isin(saved_starters)]
                else:
                    nc.subheader(f"Projected Lineup — {my_team['abbreviation']}")
                    nc.caption("Select 5 starters in Game Day to see your lineup here.")
                    display_df = roster.nlargest(5, 'OVERALL')
                injured_names_set = st.session_state.injured_list
                for _, row in display_df.iterrows():
                    _render_player_card(col_yours, row, injured_list=injured_names_set)
                    col_yours.write("")

            with col_theirs:
                lc, nc = st.columns([1, 4])
                lc.image(team_logo_url(next_opp_id), width=50)
                nc.subheader(f"Projected Lineup — {opp_team_info['abbreviation']}")
                for _, row in opp_starters.iterrows():
                    _render_player_card(col_theirs, row)
                    col_theirs.write("")

            st.divider()

            # ── Scouting Report ───────────────────────────────────────────
            st.subheader("Scouting Report")
            opp_top_scorer = opp_starters.nlargest(1, 'PTS').iloc[0]

            advice_lines = []
            if opp_avg_ovr > my_avg_ovr + 5:
                advice_lines.append(
                    f"⚠️ **Tough matchup.** {opp_team_info['full_name']} is significantly stronger "
                    f"({opp_avg_ovr} vs your {my_avg_ovr}). Consider **Grit & Grind** to slow the game down."
                )
            elif my_avg_ovr > opp_avg_ovr + 5:
                advice_lines.append(
                    f"✅ **Favorable matchup.** You're the stronger team ({my_avg_ovr} vs {opp_avg_ovr}). "
                    f"**Pace & Space** could blow this one open."
                )
            else:
                advice_lines.append(
                    f"⚖️ **Even matchup.** This is close ({my_avg_ovr} vs {opp_avg_ovr}). "
                    f"**Balanced** or lean into your healthiest players."
                )

            advice_lines.append(
                f"🎯 Watch out for **{opp_top_scorer['PLAYER']}** "
                f"({opp_top_scorer['PTS']:.1f} PPG, OVR {overall_badge(int(opp_top_scorer['OVERALL']))}) "
                f"— their primary scorer."
            )

            for line in advice_lines:
                st.markdown(line)
