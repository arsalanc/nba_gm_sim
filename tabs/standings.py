import streamlit as st

from utils import CONFERENCE, team_logo_url, save_state
from engine import generate_playoff_bracket


def render(my_team, current_team_id, all_teams, all_stats, games_played, season_phase, season_length=82):
    st.subheader("League Standings")
    standings = st.session_state.get('standings', {})
    team_map_by_id = {t['id']: t for t in all_teams}

    if not standings or all(s['w'] + s['l'] == 0 for s in standings.values()):
        st.info("Play some games to see standings.")
    else:
        st.write(f"**Game {games_played} of {season_length}**")
        col_east, col_west = st.columns(2)

        for conf, col in [('East', col_east), ('West', col_west)]:
            with col:
                st.markdown(f"### {'Eastern' if conf == 'East' else 'Western'} Conference")
                conf_teams = [tid for tid in standings if CONFERENCE.get(tid) == conf]
                conf_teams.sort(
                    key=lambda t: (
                        standings[t]['w'] / max(standings[t]['w'] + standings[t]['l'], 1),
                        standings[t]['w'],
                    ),
                    reverse=True,
                )

                if conf_teams:
                    leader_w = standings[conf_teams[0]]['w']
                    leader_l = standings[conf_teams[0]]['l']

                for rank, tid in enumerate(conf_teams, 1):
                    t_info = team_map_by_id.get(tid)
                    if not t_info:
                        continue
                    tw = standings[tid]['w']
                    tl = standings[tid]['l']
                    pct = tw / max(tw + tl, 1)
                    gb = ((leader_w - tw) + (tl - leader_l)) / 2

                    # Playoff cutoff line
                    if rank == 9:
                        st.divider()
                        st.caption("— Playoff cutoff —")

                    is_user = (tid == current_team_id)
                    prefix = "👉 " if is_user else ""
                    rc = st.columns([0.5, 0.7, 3, 1, 1, 1, 1])
                    rc[0].write(f"**{rank}**")
                    rc[1].image(team_logo_url(tid), width=30)
                    name_str = f"**{t_info['abbreviation']}**" if is_user else t_info['abbreviation']
                    rc[2].write(f"{prefix}{name_str}")
                    rc[3].write(str(tw))
                    rc[4].write(str(tl))
                    rc[5].write(f"{pct:.3f}")
                    rc[6].write(f"{gb:.1f}" if gb > 0 else "—")

        # Playoffs pending — show qualification and generate bracket
        if season_phase == 'playoffs_pending':
            st.divider()
            st.subheader("🏆 Playoff Picture")

            bracket = generate_playoff_bracket(standings, all_teams)
            st.session_state.playoff_bracket = bracket

            # Check if user qualifies
            user_conf = CONFERENCE.get(current_team_id, 'East')
            conf_teams = [tid for tid in standings if CONFERENCE.get(tid) == user_conf]
            conf_teams.sort(
                key=lambda t: (
                    standings[t]['w'] / max(standings[t]['w'] + standings[t]['l'], 1),
                    standings[t]['w'],
                ),
                reverse=True,
            )
            user_seed = next((i for i, tid in enumerate(conf_teams, 1) if tid == current_team_id), 99)

            if user_seed <= 8:
                st.success(f"🎉 Your team clinched the **#{user_seed} seed** in the {user_conf}ern Conference!")
                st.session_state.season_phase = 'playoffs_user'
                # Set up first series
                for matchup in bracket[user_conf]['round1']:
                    if current_team_id in matchup:
                        opp = matchup[1] if matchup[0] == current_team_id else matchup[0]
                        st.session_state.current_series = {
                            'opponent_id': opp, 'user_wins': 0, 'opp_wins': 0,
                            'round': 'round1',
                        }
                        break
            else:
                st.error(f"Your team finished **#{user_seed}** — missed the playoffs.")
                st.session_state.season_phase = 'playoffs_spectate'

            save_state()
            st.rerun()

        # Show bracket summary if playoffs are underway
        if season_phase in ('playoffs_user', 'playoffs_spectate') and st.session_state.playoff_bracket:
            st.divider()
            st.subheader("🏆 Playoff Bracket")
            bracket = st.session_state.playoff_bracket

            for conf in ('East', 'West'):
                st.markdown(f"#### {'Eastern' if conf == 'East' else 'Western'} Conference")
                conf_data = bracket[conf]

                for round_name, label in [('round1', 'First Round'), ('round2', 'Semifinals'),
                                          ('conf_finals', 'Conference Finals')]:
                    matchups = conf_data.get(round_name, [])
                    if not matchups:
                        continue
                    st.caption(label)
                    for matchup in matchups:
                        a_id, b_id = matchup
                        key = f"{a_id}v{b_id}"
                        series = bracket['series'].get(key, {})
                        a_info = team_map_by_id.get(a_id, {})
                        b_info = team_map_by_id.get(b_id, {})
                        wa = series.get('wins_a', 0)
                        wb = series.get('wins_b', 0)
                        winner = series.get('winner')
                        a_name = a_info.get('abbreviation', '?')
                        b_name = b_info.get('abbreviation', '?')
                        if winner:
                            w_name = team_map_by_id.get(winner, {}).get('abbreviation', '?')
                            st.write(f"~~{a_name}~~ {wa} — {wb} ~~{b_name}~~ → **{w_name}** ✅"
                                     if winner != a_id else
                                     f"**{a_name}** {wa} — {wb} ~~{b_name}~~ ✅")
                        else:
                            st.write(f"{a_name} {wa} — {wb} {b_name}")

            if bracket.get('finals'):
                st.markdown("#### NBA Finals")
                a_id, b_id = bracket['finals']
                key = f"{a_id}v{b_id}"
                series = bracket['series'].get(key, {})
                a_info = team_map_by_id.get(a_id, {})
                b_info = team_map_by_id.get(b_id, {})
                wa = series.get('wins_a', 0)
                wb = series.get('wins_b', 0)
                winner = series.get('winner')
                if winner:
                    w_info = team_map_by_id.get(winner, {})
                    st.success(f"🏆 **{w_info.get('full_name', '?')}** are your NBA Champions!")
                else:
                    st.write(f"{a_info.get('abbreviation', '?')} {wa} — {wb} {b_info.get('abbreviation', '?')}")

            if bracket.get('champion'):
                champ_info = team_map_by_id.get(bracket['champion'], {})
                st.balloons()
                st.success(f"🏆🏆🏆 **{champ_info.get('full_name', '?')}** WIN THE NBA CHAMPIONSHIP! 🏆🏆🏆")

                if st.button("🔄 Start New Season"):
                    st.session_state.results = []
                    st.session_state.season_pts = {}
                    st.session_state.injured_list = {}
                    st.session_state.standings = {t['id']: {'w': 0, 'l': 0} for t in all_teams}
                    st.session_state.games_played = 0
                    st.session_state.season_phase = 'regular'
                    st.session_state.playoff_bracket = None
                    st.session_state.current_series = None
                    st.session_state.last_game_result = None
                    st.session_state.batch_results = None
                    st.session_state.season_stamina = {}
                    st.session_state.trade_cooldown = 0
                    save_state()
                    st.rerun()
