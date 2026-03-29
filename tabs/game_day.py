import time
import re

import streamlit as st
import plotly.graph_objects as go

from utils import (
    team_logo_url, player_img_url, overall_badge, fmt_salary, save_state, SALARY_CAP,
)
from engine import (
    simulate_game, post_game_updates, generate_round_matchups, find_user_matchup,
    simulate_other_games, update_standings, auto_select_lineup,
    init_live_game, simulate_quarter, apply_user_subs, finalize_live_game,
)
from playoff_logic import _sim_playoff_round, _finish_user_series


def render(my_team, current_team_id, roster, all_teams, all_stats,
           season_phase, games_played, difficulty, hard, season_length=82):
    live = st.session_state.get('live_game')

    # ── LIVE GAME IN PROGRESS ────────────────────────────────────────────
    if live and not live.get('finished'):
        lg = live
        q = lg['quarter']
        is_ot = q > 4
        q_label = f"OT{q - 4}" if is_ot else f"Quarter {q}"

        # Scoreboard
        st.subheader(f"🏀 {lg['my_team_abbr']} vs {lg['opp_team_abbr']} — {q_label}")
        sc_my, sc_vs, sc_opp = st.columns([3, 1, 3])
        with sc_my:
            lc, mc = st.columns([1, 2])
            lc.image(team_logo_url(lg['my_team_id']), width=60)
            mc.metric(lg['my_team_abbr'], lg['my_score'])
        sc_vs.markdown(
            "<div style='text-align:center;padding-top:12px;font-size:1rem;font-weight:bold'>"
            f"{'OT' + str(q-4) if is_ot else 'Q' + str(q)}</div>",
            unsafe_allow_html=True,
        )
        with sc_opp:
            lc, mc = st.columns([1, 2])
            lc.image(team_logo_url(lg['opponent_id']), width=60)
            mc.metric(lg['opp_team_abbr'], lg['opp_score'])

        # Quarter-by-quarter scores
        if lg['quarter_scores']:
            q_cols = st.columns(len(lg['quarter_scores']) + 1)
            for qi, (mq, oq) in enumerate(lg['quarter_scores']):
                ql = f"OT{qi - 3}" if qi >= 4 else f"Q{qi + 1}"
                q_cols[qi].caption(f"**{ql}**\n{mq} - {oq}")
            q_cols[-1].caption(f"**Total**\n{lg['my_score']} - {lg['opp_score']}")

        st.divider()

        # Court view
        st.markdown(
            '<div style="background:#1a472a;border:3px solid white;border-radius:12px;'
            'padding:15px 10px 10px;text-align:center;">'
            '<div style="border:2px solid rgba(255,255,255,0.5);width:35%;margin:auto;'
            'height:40px;border-radius:0 0 50% 50%;margin-bottom:8px;"></div>'
            '<div style="color:rgba(255,255,255,0.4);font-size:0.8rem;">ON COURT</div></div>',
            unsafe_allow_html=True,
        )
        court_cols = st.columns(5)
        for ci, p in enumerate(lg['my_on_court'][:5]):
            with court_cols[ci]:
                st.image(player_img_url(p['player_id']), width=55)
                st.caption(f"**{p['name'].split()[-1]}**\n`{p['position']}`")
                stam = int(p['stamina'])
                stam_icon = "🟢" if stam >= 60 else "🟡" if stam >= 30 else "🔴"
                st.progress(max(stam, 0) / 100)
                st.caption(f"{stam_icon} {stam}% · {p['game_pts']} pts")

        st.divider()

        # Strategy change
        new_tactic = st.radio(
            "Strategy for next quarter:",
            ["Balanced", "Pace & Space", "Grit & Grind"],
            index=["Balanced", "Pace & Space", "Grit & Grind"].index(lg['tactic']),
            horizontal=True,
            key="live_tactic",
        )
        lg['tactic'] = new_tactic

        # Substitution panel
        st.subheader("↔ Substitutions")
        sub_col1, sub_col2 = st.columns(2)
        with sub_col1:
            st.caption("**On Court**")
            on_court_names = [p['name'] for p in lg['my_on_court']]
            sub_out = st.selectbox("Sub out:", on_court_names, key="sub_out")
        with sub_col2:
            st.caption("**Bench**")
            bench_names = [f"{p['name']} ({int(p['stamina'])}%)" for p in lg['my_bench']]
            if bench_names:
                sub_in_idx = st.selectbox("Sub in:", range(len(bench_names)),
                                          format_func=lambda i: bench_names[i], key="sub_in")
                sub_in_name = lg['my_bench'][sub_in_idx]['name'] if bench_names else None
            else:
                st.caption("No bench players available")
                sub_in_name = None

        if sub_in_name and st.button("✅ Confirm Substitution", key="confirm_sub"):
            apply_user_subs(lg, sub_out, sub_in_name)
            save_state()
            st.rerun()

        st.divider()

        # Play-by-play log from previous quarters
        if lg['play_by_play']:
            with st.expander(f"Play-by-play (Q1–Q{q-1})", expanded=False):
                for event in lg['play_by_play'][-50:]:
                    st.text(event)

        # Action button — play next quarter
        btn_label = f"▶️ Play {'Overtime' if is_ot else q_label}"
        if st.button(btn_label, key="play_quarter", type="primary"):
            events = simulate_quarter(lg)
            # Animate play-by-play
            pbp_container = st.empty()
            displayed = []
            for event in events:
                displayed.append(event)
                pbp_container.markdown("```\n" + "\n".join(displayed[-10:]) + "\n```")
                time.sleep(0.12)
            st.session_state.live_game = lg
            save_state()
            st.rerun()

    # ── LIVE GAME FINISHED — show final results button ───────────────────
    elif live and live.get('finished'):
        lg = live
        st.subheader(f"🏀 Final: {lg['my_team_abbr']} {lg['my_score']} — {lg['opp_team_abbr']} {lg['opp_score']}")

        # Quarter scores
        if lg['quarter_scores']:
            q_cols = st.columns(len(lg['quarter_scores']) + 1)
            for qi, (mq, oq) in enumerate(lg['quarter_scores']):
                ql = f"OT{qi - 3}" if qi >= 4 else f"Q{qi + 1}"
                q_cols[qi].caption(f"**{ql}**\n{mq} - {oq}")
            q_cols[-1].caption(f"**Total**\n{lg['my_score']} - {lg['opp_score']}")

        # Full play-by-play
        with st.expander("Full play-by-play"):
            for event in lg['play_by_play']:
                st.text(event)

        if st.button("📊 View Final Results & Continue", type="primary"):
            my_score, opp_score, box_score, injury_reports, sub_reports, opp_name, opp_box_score = finalize_live_game(lg)
            res = "W" if my_score > opp_score else "L"
            st.session_state.results.append(res)
            post_game_updates([], [], roster)

            # Season points
            for p in box_score:
                if int(p['PLAYER_ID']) == 0:
                    continue
                st.session_state.season_pts[p['Player']] = (
                    st.session_state.season_pts.get(p['Player'], 0) + p['PTS']
                )

            played_opp_id = lg['opponent_id']
            st.session_state.last_game_result = {
                'final_score': my_score, 'final_opp': opp_score,
                'res': res, 'box_score': box_score, 'opp_box_score': opp_box_score,
                'injury_reports': injury_reports, 'sub_reports': sub_reports,
                'opp_name': opp_name, 'played_opp_id': played_opp_id,
                'play_by_play': lg.get('play_by_play', []),
                'my_team_abbr': lg.get('my_team_abbr', ''),
                'opp_team_abbr': lg.get('opp_team_abbr', ''),
            }
            if res == 'W':
                st.session_state.show_balloons = True

            # Update standings if regular season
            if season_phase == 'regular' and games_played < season_length:
                matchups = generate_round_matchups(all_teams, games_played)
                other_results = simulate_other_games(matchups, current_team_id, all_stats)
                opp_res = 'L' if res == 'W' else 'W'
                all_results = {current_team_id: res, played_opp_id: opp_res, **other_results}
                update_standings(st.session_state.standings, all_results)
                st.session_state.games_played += 1
                if st.session_state.games_played >= season_length:
                    st.session_state.season_phase = 'playoffs_pending'
            elif season_phase == 'playoffs_user':
                series = st.session_state.current_series
                bracket = st.session_state.playoff_bracket
                if series:
                    if res == 'W':
                        series['user_wins'] += 1
                    else:
                        series['opp_wins'] += 1
                    if series['user_wins'] == 4 or series['opp_wins'] == 4:
                        user_won = series['user_wins'] == 4
                        _finish_user_series(bracket, series, current_team_id, user_won, all_stats)
                    else:
                        st.session_state.current_series = series

            st.session_state.live_game = None
            st.session_state.batch_results = None
            save_state()
            st.rerun()

    # ── NO LIVE GAME — normal lineup/sim flow ────────────────────────────
    else:
        injured_names = list(st.session_state.injured_list.keys())
        healthy_roster = roster[~roster['PLAYER'].isin(injured_names)].sort_values('PTS', ascending=False)

        st.subheader("Pick Your Lineup")
        st.caption("Check up to 5 players to start. Top 5 scorers are pre-selected.")

        suggested = healthy_roster.nlargest(5, 'PTS')['PLAYER'].tolist()
        starters = []
        card_cols = st.columns(5)
        for i, (_, row) in enumerate(healthy_roster.head(10).iterrows()):
            col = card_cols[i % 5]
            pos = row.get('POSITION', '?') or '?'
            col.image(player_img_url(int(row['PLAYER_ID'])), width=90)
            selected = col.checkbox(
                row['PLAYER'],
                value=row['PLAYER'] in suggested,
                key=f"starter_{row['PLAYER']}",
            )
            col.caption(
                f"`{pos}` · OVR {overall_badge(int(row['OVERALL']))}  \n"
                f"{row['PTS']:.1f} PPG · {fmt_salary(row['SALARY'])}"
            )
            if selected:
                starters.append(row['PLAYER'])

        n = len(starters)
        if n > 0:
            starter_sal = roster[roster['PLAYER'].isin(starters)]['SALARY'].sum()
            status = f"{n}/5 selected · {fmt_salary(starter_sal)}"
            if n == 5 and starter_sal > SALARY_CAP:
                st.warning(f"⚠️ Cap Violation — {status}")
            elif n == 5:
                st.success(f"✅ Lineup locked — {status}")
            else:
                st.info(f"{status}")

        st.subheader("📋 Game Plan")
        tactic = st.radio("Select Strategy:", ["Balanced", "Pace & Space", "Grit & Grind"], horizontal=True)
        st.caption({
            "Balanced": "1.0× offense and defense.",
            "Pace & Space": "1.2× your score, 1.1× opponent score. High-risk, high-reward.",
            "Grit & Grind": "0.9× your score, 0.8× opponent score. Defensive identity, more stamina drain.",
        }[tactic])

        if season_phase == 'playoffs_spectate':
            st.info("🏁 Your season is over. Watch the playoffs unfold from the **Standings** tab.")
            bracket = st.session_state.playoff_bracket
            if bracket and not bracket.get('champion'):
                if st.button("📺 Simulate Next Playoff Round"):
                    _sim_playoff_round(bracket, all_stats)
                    save_state()
                    st.rerun()

        elif season_phase == 'playoffs_user':
            series = st.session_state.current_series
            bracket = st.session_state.playoff_bracket
            if series and bracket and not bracket.get('champion') and series['user_wins'] < 4 and series['opp_wins'] < 4:
                opp_id = series['opponent_id']
                opp_info = next((t for t in all_teams if t['id'] == opp_id), None)
                round_labels = {'round1': 'First Round', 'round2': 'Semifinals',
                                'conf_finals': 'Conference Finals', 'finals': 'NBA Finals'}
                st.subheader(f"🏀 {round_labels.get(series['round'], 'Playoffs')}")
                if opp_info:
                    lc, mc = st.columns([1, 4])
                    lc.image(team_logo_url(opp_id), width=70)
                    mc.write(f"**vs {opp_info['full_name']}**")
                    mc.write(f"Series: {my_team['abbreviation']} **{series['user_wins']}** — "
                             f"**{series['opp_wins']}** {opp_info['abbreviation']}")

                pl_col1, pl_col2 = st.columns(2)
                sim_playoff = pl_col1.button("🏟️ Sim Playoff Game")
                live_playoff = pl_col2.button("🎮 Play Live Playoff Game")

                if sim_playoff or live_playoff:
                    if len(starters) != 5:
                        st.error("Select exactly 5 starters.")
                    elif live_playoff:
                        lineup_df = roster[roster['PLAYER'].isin(starters)]
                        lg = init_live_game(lineup_df, roster, all_stats, all_teams,
                                            current_team_id, series['opponent_id'], tactic,
                                            difficulty=difficulty)
                        st.session_state.live_game = lg
                        save_state()
                        st.rerun()
                    else:
                        lineup_df = roster[roster['PLAYER'].isin(starters)]
                        if hard:
                            p_mod = 1.1 if tactic == "Pace & Space" else 0.85 if tactic == "Grit & Grind" else 1.0
                            o_mod = 1.1 if tactic == "Pace & Space" else 0.85 if tactic == "Grit & Grind" else 1.0
                        else:
                            p_mod = 1.2 if tactic == "Pace & Space" else 0.9 if tactic == "Grit & Grind" else 1.0
                            o_mod = 1.1 if tactic == "Pace & Space" else 0.8 if tactic == "Grit & Grind" else 1.0

                        score, opp_score, box_score, injury_reports, sub_reports, opp_name, opp_box_score = simulate_game(
                            lineup_df, roster, tactic, all_stats, all_teams,
                            current_team_id, [],
                            opponent_team_id=series['opponent_id'],
                            difficulty=difficulty,
                        )
                        final_score = int(score * p_mod)
                        final_opp = int(opp_score * o_mod)
                        res = "W" if final_score > final_opp else "L"

                        starter_names_list = lineup_df['PLAYER'].tolist()
                        post_game_updates(starter_names_list, [], roster)

                        if res == 'W':
                            series['user_wins'] += 1
                        else:
                            series['opp_wins'] += 1

                        st.session_state.last_game_result = {
                            'final_score': final_score, 'final_opp': final_opp,
                            'res': res, 'box_score': box_score, 'opp_box_score': opp_box_score,
                            'injury_reports': injury_reports, 'sub_reports': sub_reports,
                            'opp_name': opp_name, 'played_opp_id': series['opponent_id'],
                        }
                        if res == 'W':
                            st.session_state.show_balloons = True

                        # Check if series is over
                        if series['user_wins'] == 4 or series['opp_wins'] == 4:
                            user_won = series['user_wins'] == 4
                            _finish_user_series(bracket, series, current_team_id, user_won, all_stats)
                        else:
                            st.session_state.current_series = series

                        save_state()
                        st.rerun()
            else:
                if bracket and bracket.get('champion'):
                    champ = next((t for t in all_teams if t['id'] == bracket['champion']), None)
                    champ_name = champ['full_name'] if champ else '?'
                    if bracket['champion'] == current_team_id:
                        st.success(f"🏆 Congratulations! You are the NBA Champions!")
                    else:
                        st.info(f"🏆 The **{champ_name}** are your NBA Champions. Check the **Bracket** tab.")
                else:
                    st.info("Check the **Bracket** tab for playoff results.")

        elif games_played >= season_length:
            st.info("🏁 Regular season is complete! Head to **Standings** to see playoff picture.")
        else:
            remaining = season_length - games_played
            live_col, sim_col1, sim_col2, sim_col3 = st.columns(4)
            live_btn = live_col.button("🎮 Play Live", key="play_live",
                                       disabled=remaining < 1)
            sim_1 = sim_col1.button("🏟️ Sim 1 Game", key="sim_1",
                                     disabled=remaining < 1)
            sim_5 = sim_col2.button("⏩ Sim 5 Games", key="sim_5",
                                     disabled=remaining < 1)
            sim_10 = sim_col3.button("⏭️ Sim 10 Games", key="sim_10",
                                      disabled=remaining < 1)

            if live_btn:
                if len(starters) != 5:
                    st.error("Select exactly 5 starters.")
                else:
                    lineup_df = roster[roster['PLAYER'].isin(starters)]
                    gp = st.session_state.games_played
                    matchups = generate_round_matchups(all_teams, gp)
                    opp_id, _ = find_user_matchup(matchups, current_team_id)
                    lg = init_live_game(lineup_df, roster, all_stats, all_teams,
                                        current_team_id, opp_id, tactic,
                                        difficulty=difficulty)
                    st.session_state.live_game = lg
                    save_state()
                    st.rerun()

            num_games = 0
            if sim_1: num_games = min(1, remaining)
            elif sim_5: num_games = min(5, remaining)
            elif sim_10: num_games = min(10, remaining)

            if num_games > 0:
                if len(starters) != 5:
                    st.error("Select exactly 5 starters to continue.")
                else:
                    if hard:
                        p_mod = 1.1 if tactic == "Pace & Space" else 0.85 if tactic == "Grit & Grind" else 1.0
                        o_mod = 1.1 if tactic == "Pace & Space" else 0.85 if tactic == "Grit & Grind" else 1.0
                    else:
                        p_mod = 1.2 if tactic == "Pace & Space" else 0.9 if tactic == "Grit & Grind" else 1.0
                        o_mod = 1.1 if tactic == "Pace & Space" else 0.8 if tactic == "Grit & Grind" else 1.0
                    batch_results = []

                    for game_i in range(num_games):
                        gp = st.session_state.games_played
                        if gp >= season_length:
                            break

                        # Game 0 uses manual lineup; subsequent games auto-select
                        if game_i == 0:
                            lineup_df = roster[roster['PLAYER'].isin(starters)]
                            current_rested = []
                        else:
                            lineup_df, current_rested = auto_select_lineup(
                                roster, st.session_state.injured_list
                            )

                        # Get schedule-based opponent
                        matchups = generate_round_matchups(all_teams, gp)
                        opp_id, _ = find_user_matchup(matchups, current_team_id)

                        score, opp_score, box_score, injury_reports, sub_reports, opp_name, opp_box_score = simulate_game(
                            lineup_df, roster, tactic, all_stats, all_teams,
                            current_team_id, current_rested,
                            opponent_team_id=opp_id,
                            difficulty=difficulty,
                        )

                        final_score = int(score * p_mod)
                        final_opp = int(opp_score * o_mod)
                        res = "W" if final_score > final_opp else "L"
                        st.session_state.results.append(res)

                        starter_names = lineup_df['PLAYER'].tolist()
                        post_game_updates(starter_names, current_rested, roster)

                        # Accumulate season points
                        for p in box_score:
                            if int(p['PLAYER_ID']) == 0:
                                continue
                            clean_name = p['Player'].split(" (sub")[0].replace("↔ ", "").strip()
                            if " (sub for " in clean_name:
                                clean_name = clean_name.split(" (sub for ")[0]
                            st.session_state.season_pts[clean_name] = (
                                st.session_state.season_pts.get(clean_name, 0) + p['PTS']
                            )

                        # Sim the other 14 matchups in this round
                        other_results = simulate_other_games(matchups, current_team_id, all_stats)
                        opp_res = 'L' if res == 'W' else 'W'
                        all_results = {current_team_id: res, opp_id: opp_res, **other_results}
                        update_standings(st.session_state.standings, all_results)

                        st.session_state.games_played += 1

                        batch_results.append({
                            'final_score': final_score,
                            'final_opp': final_opp,
                            'res': res,
                            'box_score': box_score,
                            'opp_box_score': opp_box_score,
                            'injury_reports': injury_reports,
                            'sub_reports': sub_reports,
                            'opp_name': opp_name,
                            'played_opp_id': opp_id,
                        })

                    # Store the last game for detailed display and batch summary
                    if batch_results:
                        st.session_state.last_game_result = batch_results[-1]
                        st.session_state.batch_results = batch_results
                        batch_w = sum(1 for g in batch_results if g['res'] == 'W')
                        if batch_w == len(batch_results):
                            st.session_state.show_balloons = True

                        # Check if season just ended
                        if st.session_state.games_played >= season_length:
                            st.session_state.season_phase = 'playoffs_pending'

                        save_state()
                        st.rerun()

        # ── Last game result (rendered from session state after rerun) ─────────
        if st.session_state.get('show_balloons'):
            st.balloons()
            st.session_state.show_balloons = False

        # Batch summary (if multiple games were simmed)
        batch = st.session_state.get('batch_results')
        if batch and len(batch) > 1:
            batch_w = sum(1 for g in batch if g['res'] == 'W')
            batch_l = len(batch) - batch_w
            st.subheader(f"Batch Results: {batch_w}W — {batch_l}L in {len(batch)} games")
            with st.expander("Game-by-game scores"):
                for i, g in enumerate(batch):
                    icon = "✅" if g['res'] == 'W' else "❌"
                    st.write(f"{icon} Game {games_played - len(batch) + i + 1}: "
                             f"{my_team['abbreviation']} {g['final_score']} — "
                             f"{g['opp_name']} {g['final_opp']}")
            st.caption("Detailed box score shown for the last game:")

        r = st.session_state.get('last_game_result')
        if r:
            sc_my, sc_vs, sc_opp = st.columns([3, 1, 3])
            with sc_my:
                lc, mc = st.columns([1, 2])
                lc.image(team_logo_url(current_team_id), width=70)
                mc.metric(my_team['abbreviation'], r['final_score'],
                          delta=r['final_score'] - r['final_opp'])
            sc_vs.markdown(
                "<div style='text-align:center;padding-top:16px;font-size:1.2rem;font-weight:bold'>FINAL</div>",
                unsafe_allow_html=True,
            )
            with sc_opp:
                lc, mc = st.columns([1, 2])
                if r['played_opp_id']:
                    lc.image(team_logo_url(r['played_opp_id']), width=70)
                mc.metric(r['opp_name'], r['final_opp'])

            for ir in r['injury_reports']:
                st.warning(f"🚑 {ir}")

            st.subheader("Box Score")
            bs_tab_my, bs_tab_opp, bs_tab_flow = st.tabs([f"🏠 {my_team['abbreviation']}", f"🏀 {r['opp_name']}", "📈 Game Flow"])

            def _render_box_score_table(box_rows):
                hdr = st.columns([1, 3, 1, 1, 1, 1, 1, 1, 2])
                for col, label in zip(hdr, ["", "Player", "PTS", "REB", "AST", "STL", "BLK", "TOV", "Stamina"]):
                    col.write(f"**{label}**")
                st.divider()
                for p in box_rows:
                    rc = st.columns([1, 3, 1, 1, 1, 1, 1, 1, 2])
                    pid = int(p['PLAYER_ID'])
                    if pid == 0:
                        rc[0].write("🪑")
                    else:
                        rc[0].image(player_img_url(pid), width=50)
                    rc[1].write(p['Player'])
                    rc[2].write(str(p['PTS']))
                    rc[3].write(str(p.get('REB', 0)))
                    rc[4].write(str(p.get('AST', 0)))
                    rc[5].write(str(p.get('STL', 0)))
                    rc[6].write(str(p.get('BLK', 0)))
                    rc[7].write(str(p.get('TOV', 0)))
                    stam = p['Stamina Left']
                    icon = "🟢" if stam >= 60 else "🟡" if stam >= 30 else "🔴"
                    rc[8].write(f"{icon} {stam}%")

            with bs_tab_my:
                _render_box_score_table(r['box_score'])
            with bs_tab_opp:
                _render_box_score_table(r.get('opp_box_score', []))
            with bs_tab_flow:
                pbp = r.get('play_by_play', [])
                my_abbr_flow = r.get('my_team_abbr', '')
                opp_abbr_flow = r.get('opp_team_abbr', r['opp_name'])
                if not pbp:
                    st.info("Game flow is only available for live games.")
                else:
                    my_pts_series, opp_pts_series = [], []
                    quarter_breaks = []
                    pattern = re.compile(r'\((\w+) (\d+), (\w+) (\d+)\)')
                    prev_q = None
                    for i, event in enumerate(pbp):
                        m = pattern.search(event)
                        if not m:
                            continue
                        a_abbr, a_pts, b_abbr, b_pts = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
                        if a_abbr == my_abbr_flow:
                            my_pts_series.append(a_pts)
                            opp_pts_series.append(b_pts)
                        else:
                            my_pts_series.append(b_pts)
                            opp_pts_series.append(a_pts)
                        # Detect quarter breaks from event label
                        q_label = event.split(' ')[0]
                        if prev_q and q_label != prev_q and not q_label.startswith('↔') and not q_label.startswith('🚨'):
                            quarter_breaks.append(len(my_pts_series) - 1)
                        prev_q = q_label

                    if my_pts_series:
                        fig = go.Figure()
                        xs = list(range(len(my_pts_series)))
                        fig.add_trace(go.Scatter(
                            x=xs, y=my_pts_series,
                            mode='lines', name=my_abbr_flow,
                            line=dict(color='#4da6ff', width=2),
                        ))
                        fig.add_trace(go.Scatter(
                            x=xs, y=opp_pts_series,
                            mode='lines', name=opp_abbr_flow,
                            line=dict(color='#aaaaaa', width=2, dash='dot'),
                        ))
                        for qb in quarter_breaks:
                            fig.add_vline(x=qb, line_dash='dash', line_color='rgba(255,255,255,0.3)', line_width=1)
                        lead_changes = sum(
                            1 for i in range(1, len(my_pts_series))
                            if (my_pts_series[i] > opp_pts_series[i]) != (my_pts_series[i-1] > opp_pts_series[i-1])
                        )
                        fig.update_layout(
                            title=dict(text=f"{my_abbr_flow} {r['final_score']} — {opp_abbr_flow} {r['final_opp']}  ·  {lead_changes} lead changes", font=dict(size=14)),
                            xaxis_title="Possession",
                            yaxis_title="Score",
                            plot_bgcolor='#0e1117',
                            paper_bgcolor='#0e1117',
                            font=dict(color='white'),
                            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
                            margin=dict(l=40, r=20, t=60, b=40),
                            height=350,
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No scoring events to chart.")
