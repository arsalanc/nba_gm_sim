import streamlit as st
import pandas as pd
import os

from utils import (
    SAVE_FILE, player_img_url, team_logo_url, fmt_salary, overall_badge,
    save_state, load_state, load_nba_data, evaluate_trade,
    CONFERENCE, compute_team_strength,
)
from engine import (
    simulate_game, post_game_updates, generate_round_matchups,
    find_user_matchup, simulate_other_games, update_standings,
    auto_select_lineup, generate_playoff_bracket, simulate_playoff_series,
)

# --- CONSTANTS ---
SALARY_CAP = 140_700_000
LUXURY_TAX = 170_814_000


def _advance_bracket(bracket, conf, current_round):
    """Advance winners of a completed round to the next round. Returns next round name or None."""
    round_order = ['round1', 'round2', 'conf_finals']
    conf_data = bracket[conf]
    matchups = conf_data[current_round]

    winners = []
    for a_id, b_id in matchups:
        key = f"{a_id}v{b_id}"
        series = bracket['series'].get(key, {})
        if series.get('winner'):
            winners.append(series['winner'])

    if len(winners) != len(matchups):
        return current_round  # not all series finished yet

    idx = round_order.index(current_round)
    if idx + 1 < len(round_order):
        next_round = round_order[idx + 1]
        next_matchups = [(winners[i], winners[i + 1]) for i in range(0, len(winners), 2)]
        conf_data[next_round] = next_matchups
        for a, b in next_matchups:
            bracket['series'][f"{a}v{b}"] = {'a': a, 'b': b, 'wins_a': 0, 'wins_b': 0, 'winner': None}
        return next_round
    else:
        # Conference finals just finished — this conference has a champion
        conf_data['winner'] = winners[0]
        # Check if both conferences done → set up finals
        east_w = bracket['East'].get('winner')
        west_w = bracket['West'].get('winner')
        if east_w and west_w and not bracket.get('finals'):
            bracket['finals'] = (east_w, west_w)
            bracket['series'][f"{east_w}v{west_w}"] = {
                'a': east_w, 'b': west_w, 'wins_a': 0, 'wins_b': 0, 'winner': None,
            }
        return None


def _sim_playoff_round(bracket, all_stats):
    """Simulate one full playoff round for all incomplete series (spectate mode)."""

    # Sim conference rounds
    for conf in ('East', 'West'):
        for round_name in ('round1', 'round2', 'conf_finals'):
            matchups = bracket[conf].get(round_name, [])
            for a_id, b_id in matchups:
                key = f"{a_id}v{b_id}"
                series = bracket['series'].get(key)
                if not series or series.get('winner'):
                    continue
                winner, wa, wb = simulate_playoff_series(a_id, b_id, all_stats)
                series['wins_a'] = wa
                series['wins_b'] = wb
                series['winner'] = winner
            # Try to advance
            if matchups:
                _advance_bracket(bracket, conf, round_name)

    # Sim finals if ready
    if bracket.get('finals') and not bracket.get('champion'):
        a_id, b_id = bracket['finals']
        key = f"{a_id}v{b_id}"
        series = bracket['series'].get(key)
        if series and not series.get('winner'):
            winner, wa, wb = simulate_playoff_series(a_id, b_id, all_stats)
            series['wins_a'] = wa
            series['wins_b'] = wb
            series['winner'] = winner
            bracket['champion'] = winner
            st.session_state.season_phase = 'offseason'


def _finish_user_series(bracket, series, user_team_id, user_won, all_stats):
    """Handle end of a user's playoff series — advance or eliminate."""
    opp_id = series['opponent_id']
    winner = user_team_id if user_won else opp_id

    # Update bracket series record
    # Figure out the key — user could be team a or b
    key1 = f"{user_team_id}v{opp_id}"
    key2 = f"{opp_id}v{user_team_id}"
    key = key1 if key1 in bracket['series'] else key2
    b_series = bracket['series'][key]
    if b_series['a'] == user_team_id:
        b_series['wins_a'] = series['user_wins']
        b_series['wins_b'] = series['opp_wins']
    else:
        b_series['wins_a'] = series['opp_wins']
        b_series['wins_b'] = series['user_wins']
    b_series['winner'] = winner

    if not user_won:
        # User eliminated — sim remaining playoffs
        st.session_state.season_phase = 'playoffs_spectate'
        st.session_state.current_series = None
        return

    # User won — advance bracket and find next opponent
    current_round = series['round']
    user_conf = CONFERENCE.get(user_team_id, 'East')

    # If user just won the Finals — championship!
    if current_round == 'finals':
        bracket['champion'] = user_team_id
        st.session_state.season_phase = 'offseason'
        st.session_state.current_series = None
        return

    # Sim other series in this conference round that aren't done yet
    for a_id, b_id in bracket[user_conf].get(current_round, []):
        rkey = f"{a_id}v{b_id}"
        rs = bracket['series'].get(rkey)
        if rs and not rs.get('winner'):
            w, wa, wb = simulate_playoff_series(a_id, b_id, all_stats)
            rs['wins_a'] = wa
            rs['wins_b'] = wb
            rs['winner'] = w

    # Also sim the other conference up to current progress
    other_conf = 'West' if user_conf == 'East' else 'East'
    for round_name in ('round1', 'round2', 'conf_finals'):
        for a_id, b_id in bracket[other_conf].get(round_name, []):
            rkey = f"{a_id}v{b_id}"
            rs = bracket['series'].get(rkey)
            if rs and not rs.get('winner'):
                w, wa, wb = simulate_playoff_series(a_id, b_id, all_stats)
                rs['wins_a'] = wa
                rs['wins_b'] = wb
                rs['winner'] = w
        if bracket[other_conf].get(round_name, []):
            _advance_bracket(bracket, other_conf, round_name)

    # Advance user's conference
    next_round = _advance_bracket(bracket, user_conf, current_round)

    if next_round and next_round != current_round:
        # Find user's next matchup in the next conference round
        for a_id, b_id in bracket[user_conf].get(next_round, []):
            if user_team_id in (a_id, b_id):
                new_opp = b_id if a_id == user_team_id else a_id
                st.session_state.current_series = {
                    'opponent_id': new_opp, 'user_wins': 0, 'opp_wins': 0,
                    'round': next_round,
                }
                return

    # Conference done — check if Finals are set up
    if bracket.get('finals'):
        a_id, b_id = bracket['finals']
        if user_team_id in (a_id, b_id):
            new_opp = b_id if a_id == user_team_id else a_id
            st.session_state.current_series = {
                'opponent_id': new_opp, 'user_wins': 0, 'opp_wins': 0,
                'round': 'finals',
            }
            return

# ─── APP ──────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="NBA GM Sim", layout="wide")
st.title("🏀 NBA GM Simulator")

load_state()
all_teams, all_stats = load_nba_data()

# Default session state (skipped if already loaded from save)
_defaults = {
    'my_team_id': None,
    'results': [],
    'season_pts': {},
    'injured_list': {},
    'stamina': {},
    'my_roster_overrides': {},
    'trade_history': [],
    'standings': {},
    'games_played': 0,
    'season_phase': 'regular',
    'playoff_bracket': None,
    'current_series': None,
    'last_game_result': None,   # transient — not saved to file
    'batch_results': None,      # transient — batch sim summary
    'current_starters': [],     # transient — tracks live checkbox selection
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── TEAM SELECTION ────────────────────────────────────────────────────────────
if st.session_state.my_team_id is None:
    st.subheader("Welcome, GM. Choose your franchise.")
    team_map = {t['full_name']: t['id'] for t in all_teams}
    selected = st.selectbox("Select your franchise:", sorted(team_map.keys()))
    preview_id = team_map[selected]
    logo_col, _ = st.columns([1, 4])
    logo_col.image(team_logo_url(preview_id), width=120)
    if st.button("✍️ Sign Contract"):
        st.session_state.my_team_id = team_map[selected]
        st.session_state.standings = {t['id']: {'w': 0, 'l': 0} for t in all_teams}
        save_state()
        st.rerun()

# ── GM DASHBOARD ──────────────────────────────────────────────────────────────
else:
    my_team = next(t for t in all_teams if t['id'] == st.session_state.my_team_id)
    current_team_id = int(st.session_state.my_team_id)
    overrides = st.session_state.my_roster_overrides

    # Build roster accounting for trades
    traded_away = [name for name, tid in overrides.items() if tid != current_team_id]
    acquired = [name for name, tid in overrides.items() if tid == current_team_id]
    base_roster = all_stats[all_stats['TEAM_ID'] == current_team_id].copy()
    roster = base_roster[~base_roster['PLAYER'].isin(traded_away)].copy()
    if acquired:
        acquired_df = all_stats[all_stats['PLAYER'].isin(acquired)].copy()
        roster = pd.concat([roster, acquired_df], ignore_index=True).drop_duplicates('PLAYER')

    w = st.session_state.results.count('W')
    l = st.session_state.results.count('L')

    # ── SIDEBAR ───────────────────────────────────────────────────────────────
    st.sidebar.image(team_logo_url(current_team_id), width=80)
    games_played = st.session_state.get('games_played', 0)
    season_phase = st.session_state.get('season_phase', 'regular')
    st.sidebar.header(my_team['full_name'])
    if season_phase == 'regular':
        st.sidebar.write(f"**Record:** {w}W — {l}L  ·  Game {games_played}/82")
    elif season_phase in ('playoffs_user', 'playoffs_spectate'):
        st.sidebar.write(f"**Record:** {w}W — {l}L  ·  Playoffs")
    else:
        st.sidebar.write(f"**Record:** {w}W — {l}L")

    # Salary cap
    st.sidebar.divider()
    st.sidebar.subheader("💰 Salary Cap")
    roster_salary = roster['SALARY'].sum()
    cap_pct = min(roster_salary / SALARY_CAP, 1.2)
    if roster_salary > LUXURY_TAX:
        st.sidebar.error(f"{fmt_salary(roster_salary)} / {fmt_salary(SALARY_CAP)} — Over Luxury Tax!")
    elif roster_salary > SALARY_CAP:
        st.sidebar.warning(f"{fmt_salary(roster_salary)} / {fmt_salary(SALARY_CAP)} — Over Cap")
    else:
        st.sidebar.success(f"{fmt_salary(roster_salary)} / {fmt_salary(SALARY_CAP)}")
    st.sidebar.progress(min(cap_pct, 1.0))
    st.sidebar.caption(f"Cap space: {fmt_salary(max(0, SALARY_CAP - roster_salary))}")

    # Medical report
    st.sidebar.divider()
    st.sidebar.subheader("🏥 Medical Report")
    if st.session_state.injured_list:
        for p_name, games in list(st.session_state.injured_list.items()):
            p_row = all_stats[all_stats['PLAYER'] == p_name]
            if not p_row.empty:
                pid = int(p_row.iloc[0]['PLAYER_ID'])
                img_col, txt_col = st.sidebar.columns([1, 3])
                img_col.image(player_img_url(pid), width=45)
                txt_col.error(f"**{p_name.split()[-1]}**\nOUT {games}g")
    else:
        st.sidebar.caption("No injuries")

    # Stamina tracker
    st.sidebar.divider()
    st.sidebar.subheader("🔋 Stamina Tracker")
    starters_shown = False
    for p_name, stam in st.session_state.stamina.items():
        if p_name in st.session_state.injured_list:
            continue
        icon = "🟢" if stam >= 60 else "🟡" if stam >= 30 else "🔴"
        st.sidebar.write(f"{icon} {p_name} ({stam}%)")
        st.sidebar.progress(stam / 100)
        starters_shown = True
    if not starters_shown:
        st.sidebar.caption("Play a game to see stamina.")

    st.sidebar.divider()
    if st.sidebar.button("🔄 Reset Game"):
        for k, v in _defaults.items():
            st.session_state[k] = v
        if os.path.exists(SAVE_FILE):
            os.remove(SAVE_FILE)
        st.rerun()

    # ── PRE-COMPUTE CURRENT LINEUP ────────────────────────────────────────────
    # Checkbox widget values are stored in st.session_state by key the moment
    # any widget interaction fires, so we can read them here — before the tabs
    # render — to keep Gameplan in sync on every rerun.
    _injured = list(st.session_state.injured_list.keys())
    _healthy = roster[~roster['PLAYER'].isin(_injured)].sort_values('PTS', ascending=False)
    _rested = [p for p in _healthy['PLAYER'] if st.session_state.get(f"rest_{p}", False)]
    _available = _healthy[~_healthy['PLAYER'].isin(_rested)].head(10)
    _suggested = _available.nlargest(5, 'PTS')['PLAYER'].tolist()
    st.session_state.current_starters = [
        row['PLAYER'] for _, row in _available.iterrows()
        if st.session_state.get(f"starter_{row['PLAYER']}", row['PLAYER'] in _suggested)
    ]

    # ── MAIN TABS ─────────────────────────────────────────────────────────────
    tab_gameplan, tab_game, tab_trade, tab_standings, tab_stats = st.tabs(
        ["📝 Gameplan", "🏟️ Game Day", "📋 Trade Desk", "🏆 Standings", "📊 Season Stats"]
    )

    # ── GAMEPLAN ──────────────────────────────────────────────────────────────
    with tab_gameplan:
        next_opp_id = None

        if season_phase == 'playoffs_user' and st.session_state.current_series:
            # Show playoff series opponent
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
        elif games_played >= 82:
            st.info("Regular season is over! Check the **Standings** tab for playoff picture.")
        else:
            matchups_preview = generate_round_matchups(all_teams, games_played)
            next_opp_id, _ = find_user_matchup(matchups_preview, current_team_id)

        if next_opp_id is None and season_phase == 'regular' and games_played < 82:
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
                    my_starters_default = my_lineup_df
                else:
                    my_starters_default = roster.nlargest(5, 'OVERALL')
                    my_avg_ovr = int(my_starters_default['OVERALL'].mean())
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

                def render_player_card(col, player_row, stamina_dict=None, injured_list=None):
                    ovr = int(player_row['OVERALL'])
                    name = player_row['PLAYER']
                    pid = int(player_row['PLAYER_ID'])
                    pos = player_row.get('POSITION', '?') or '?'
                    stam = stamina_dict.get(name, 100) if stamina_dict else None
                    is_injured = injured_list and name in injured_list

                    img_c, info_c = col.columns([1, 3])
                    img_c.image(player_img_url(pid), width=65)

                    label = f"**{name}**"
                    if is_injured:
                        label += f"  🏥 OUT {injured_list[name]}g"
                    info_c.markdown(label)
                    info_c.write(f"`{pos}`  {overall_badge(ovr)}")

                    stat_parts = [f"{player_row['PTS']:.1f} PPG"]
                    if 'REB' in player_row: stat_parts.append(f"{player_row['REB']:.1f} REB")
                    if 'AST' in player_row: stat_parts.append(f"{player_row['AST']:.1f} AST")
                    info_c.caption(" · ".join(stat_parts))

                    if stam is not None:
                        stam_icon = "🟢" if stam >= 60 else "🟡" if stam >= 30 else "🔴"
                        info_c.caption(f"Stamina: {stam_icon} {stam}%")

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
                        render_player_card(col_yours, row,
                                           stamina_dict=st.session_state.stamina,
                                           injured_list=injured_names_set)
                        col_yours.write("")

                with col_theirs:
                    lc, nc = st.columns([1, 4])
                    lc.image(team_logo_url(next_opp_id), width=50)
                    nc.subheader(f"Projected Lineup — {opp_team_info['abbreviation']}")
                    for _, row in opp_starters.iterrows():
                        render_player_card(col_theirs, row)
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

                low_stam = [
                    f"{r['PLAYER']} ({st.session_state.stamina.get(r['PLAYER'], 100)}%)"
                    for _, r in my_starters_default.iterrows()
                    if st.session_state.stamina.get(r['PLAYER'], 100) < 40
                ]
                if low_stam:
                    advice_lines.append(
                        f"🔴 **Fatigue alert:** {', '.join(low_stam)} are running low. "
                        f"Consider resting them or expect subs mid-game."
                    )

                for line in advice_lines:
                    st.markdown(line)

    # ── GAME DAY ──────────────────────────────────────────────────────────────
    with tab_game:
        injured_names = list(st.session_state.injured_list.keys())
        healthy_roster = roster[~roster['PLAYER'].isin(injured_names)].sort_values('PTS', ascending=False)

        st.subheader("Load Management")
        st.caption("Rest players to skip this game and gain +40 stamina. Starters only drain -15/-20 per game.")
        rest_cols = st.columns(4)
        rested_players = []
        for i, (_, row) in enumerate(healthy_roster.head(12).iterrows()):
            col = rest_cols[i % 4]
            stam = st.session_state.stamina.get(row['PLAYER'], 100)
            icon = "🟢" if stam >= 60 else "🟡" if stam >= 30 else "🔴"
            if col.checkbox(
                f"{icon} {row['PLAYER'].split()[-1]} ({stam}%)",
                key=f"rest_{row['PLAYER']}"
            ):
                rested_players.append(row['PLAYER'])

        available_players = [p for p in healthy_roster['PLAYER'].tolist() if p not in rested_players]
        available_df = healthy_roster[healthy_roster['PLAYER'].isin(available_players)]

        st.divider()
        st.subheader("Pick Your Lineup")
        st.caption("Check up to 5 players to start. Top 5 scorers are pre-selected.")

        suggested = available_df.nlargest(5, 'PTS')['PLAYER'].tolist()
        starters = []
        card_cols = st.columns(5)
        for i, (_, row) in enumerate(available_df.head(10).iterrows()):
            col = card_cols[i % 5]
            stam = st.session_state.stamina.get(row['PLAYER'], 100)
            stam_icon = "🟢" if stam >= 60 else "🟡" if stam >= 30 else "🔴"
            pos = row.get('POSITION', '?') or '?'
            col.image(player_img_url(int(row['PLAYER_ID'])), width=90)
            selected = col.checkbox(
                row['PLAYER'],
                value=row['PLAYER'] in suggested,
                key=f"starter_{row['PLAYER']}",
            )
            col.caption(
                f"`{pos}` · OVR {overall_badge(int(row['OVERALL']))}  \n"
                f"{row['PTS']:.1f} PPG · {fmt_salary(row['SALARY'])}  \n"
                f"Stamina: {stam_icon} {stam}%"
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
            if series and bracket and not bracket.get('champion'):
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

                if st.button("🏟️ Sim Playoff Game"):
                    if len(starters) != 5:
                        st.error("Select exactly 5 starters.")
                    else:
                        lineup_df = roster[roster['PLAYER'].isin(starters)]
                        p_mod = 1.2 if tactic == "Pace & Space" else 0.9 if tactic == "Grit & Grind" else 1.0
                        o_mod = 1.1 if tactic == "Pace & Space" else 0.8 if tactic == "Grit & Grind" else 1.0

                        score, opp_score, box_score, injury_reports, sub_reports, opp_name = simulate_game(
                            lineup_df, roster, tactic, all_stats, all_teams,
                            current_team_id, rested_players,
                            opponent_team_id=series['opponent_id'],
                        )
                        final_score = int(score * p_mod)
                        final_opp = int(opp_score * o_mod)
                        res = "W" if final_score > final_opp else "L"

                        starter_names_list = lineup_df['PLAYER'].tolist()
                        post_game_updates(starter_names_list, rested_players, roster)

                        if res == 'W':
                            series['user_wins'] += 1
                        else:
                            series['opp_wins'] += 1

                        st.session_state.last_game_result = {
                            'final_score': final_score, 'final_opp': final_opp,
                            'res': res, 'box_score': box_score,
                            'injury_reports': injury_reports, 'sub_reports': sub_reports,
                            'opp_name': opp_name, 'played_opp_id': series['opponent_id'],
                        }
                        if res == 'W':
                            st.session_state.show_balloons = True

                        # Check if series is over
                        if series['user_wins'] == 4 or series['opp_wins'] == 4:
                            user_won = series['user_wins'] == 4
                            _finish_user_series(bracket, series, current_team_id, user_won,
                                                all_stats)

                        st.session_state.current_series = series
                        save_state()
                        st.rerun()
            else:
                st.info("Check the **Standings** tab for playoff results.")

        elif games_played >= 82:
            st.info("🏁 Regular season is complete! Head to **Standings** to see playoff picture.")
        else:
            remaining = 82 - games_played
            sim_col1, sim_col2, sim_col3 = st.columns(3)
            sim_1 = sim_col1.button("🏟️ Sim 1 Game", key="sim_1",
                                     disabled=remaining < 1)
            sim_5 = sim_col2.button("⏩ Sim 5 Games", key="sim_5",
                                     disabled=remaining < 1)
            sim_10 = sim_col3.button("⏭️ Sim 10 Games", key="sim_10",
                                      disabled=remaining < 1)

            num_games = 0
            if sim_1: num_games = min(1, remaining)
            elif sim_5: num_games = min(5, remaining)
            elif sim_10: num_games = min(10, remaining)

            if num_games > 0:
                if len(starters) != 5:
                    st.error("Select exactly 5 starters to continue.")
                else:
                    p_mod = 1.2 if tactic == "Pace & Space" else 0.9 if tactic == "Grit & Grind" else 1.0
                    o_mod = 1.1 if tactic == "Pace & Space" else 0.8 if tactic == "Grit & Grind" else 1.0
                    batch_results = []

                    for game_i in range(num_games):
                        gp = st.session_state.games_played
                        if gp >= 82:
                            break

                        # Game 0 uses manual lineup; subsequent games auto-select
                        if game_i == 0:
                            lineup_df = roster[roster['PLAYER'].isin(starters)]
                            current_rested = rested_players
                        else:
                            lineup_df, current_rested = auto_select_lineup(
                                roster, st.session_state.injured_list, st.session_state.stamina
                            )

                        # Get schedule-based opponent
                        matchups = generate_round_matchups(all_teams, gp)
                        opp_id, _ = find_user_matchup(matchups, current_team_id)

                        score, opp_score, box_score, injury_reports, sub_reports, opp_name = simulate_game(
                            lineup_df, roster, tactic, all_stats, all_teams,
                            current_team_id, current_rested,
                            opponent_team_id=opp_id,
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
                                st.session_state.season_pts.get(clean_name, 0) + p['Points']
                            )

                        # Sim the other 14 matchups in this round
                        other_results = simulate_other_games(matchups, current_team_id, all_stats)
                        # Build full round results for standings
                        opp_res = 'L' if res == 'W' else 'W'
                        all_results = {current_team_id: res, opp_id: opp_res, **other_results}
                        update_standings(st.session_state.standings, all_results)

                        st.session_state.games_played += 1

                        batch_results.append({
                            'final_score': final_score,
                            'final_opp': final_opp,
                            'res': res,
                            'box_score': box_score,
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
                        if st.session_state.games_played >= 82:
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
            for sr in r['sub_reports']:
                st.info(sr)

            st.subheader("Box Score")
            hdr = st.columns([1, 3, 1, 1, 2])
            hdr[0].write("**Photo**")
            hdr[1].write("**Player**")
            hdr[2].write("**Pos**")
            hdr[3].write("**PTS**")
            hdr[4].write("**Stamina**")
            st.divider()
            for p in r['box_score']:
                rc = st.columns([1, 3, 1, 1, 2])
                pid = int(p['PLAYER_ID'])
                if pid == 0:
                    rc[0].write("🪑")
                else:
                    rc[0].image(player_img_url(pid), width=50)
                rc[1].write(p['Player'])
                p_row = all_stats[all_stats['PLAYER_ID'] == p['PLAYER_ID']]
                pos = p_row.iloc[0].get('POSITION', '?') if not p_row.empty else '—'
                rc[2].write(f"`{pos or '?'}`")
                rc[3].write(str(p['Points']))
                stam = p['Stamina Left']
                icon = "🟢" if stam >= 60 else "🟡" if stam >= 30 else "🔴"
                rc[4].write(f"{icon} {stam}%")

    # ── TRADE DESK ────────────────────────────────────────────────────────────
    with tab_trade:
        st.subheader("Trade Desk")
        st.caption(
            "Real NBA salary matching rules apply: incoming salary must be ≤ outgoing × 1.25 + $100K. "
            "The AI GM will reject lopsided deals."
        )

        other_teams_list = [t for t in all_teams if t['id'] != current_team_id]
        team_name_map = {t['full_name']: t for t in other_teams_list}
        partner_name = st.selectbox("Trade Partner:", sorted(team_name_map.keys()), key="trade_partner")
        partner_team = team_name_map[partner_name]
        ptl_col, _ = st.columns([1, 5])
        ptl_col.image(team_logo_url(partner_team['id']), width=80)

        # Build partner roster, excluding players already acquired by user
        partner_roster = all_stats[all_stats['TEAM_ID'] == partner_team['id']].copy()
        partner_roster = partner_roster[~partner_roster['PLAYER'].isin(acquired)]

        col_mine, col_theirs = st.columns(2)

        with col_mine:
            lc, nc = st.columns([1, 5])
            lc.image(team_logo_url(current_team_id), width=40)
            nc.write(f"**Your players** ({my_team['abbreviation']})")
            my_labels = roster.apply(
                lambda r: f"[{r.get('POSITION') or '?'}] {r['PLAYER']} — {r['PTS']:.1f} PPG, OVR {r['OVERALL']}, {fmt_salary(r['SALARY'])}", axis=1
            ).tolist()
            my_name_map = dict(zip(my_labels, roster['PLAYER'].tolist()))
            my_selections = st.multiselect(
                "Send (1–3 players):", options=my_labels, key="my_trade_players"
            )

        with col_theirs:
            lc, nc = st.columns([1, 5])
            lc.image(team_logo_url(partner_team['id']), width=40)
            nc.write(f"**{partner_name} players**")
            their_labels = partner_roster.apply(
                lambda r: f"[{r.get('POSITION') or '?'}] {r['PLAYER']} — {r['PTS']:.1f} PPG, OVR {r['OVERALL']}, {fmt_salary(r['SALARY'])}", axis=1
            ).tolist()
            their_name_map = dict(zip(their_labels, partner_roster['PLAYER'].tolist()))
            their_selections = st.multiselect(
                "Receive (1–3 players):", options=their_labels, key="their_trade_players"
            )

        if my_selections and their_selections:
            if len(my_selections) > 3 or len(their_selections) > 3:
                st.error("Maximum 3 players per side.")
            else:
                my_names = [my_name_map[l] for l in my_selections]
                their_names = [their_name_map[l] for l in their_selections]
                my_trade_df = roster[roster['PLAYER'].isin(my_names)]
                their_trade_df = partner_roster[partner_roster['PLAYER'].isin(their_names)]

                accepted, my_pts, their_pts, my_sal, their_sal = evaluate_trade(my_trade_df, their_trade_df)

                salary_limit = my_sal * 1.25 + 100_000
                st.write(
                    f"**Trade summary:** You send {fmt_salary(my_sal)} / {my_pts:.1f} PPG "
                    f"→ Receive {fmt_salary(their_sal)} / {their_pts:.1f} PPG"
                )
                if their_sal > salary_limit:
                    st.error(f"Salary mismatch: max you can receive is {fmt_salary(salary_limit)}")
                elif not accepted:
                    st.error(
                        f"{partner_name}'s GM doesn't see enough value. "
                        f"They're giving up {their_pts:.1f} PPG for your {my_pts:.1f} PPG — offer more."
                    )
                else:
                    st.success("✅ AI GM will accept this trade.")

                if st.button("📨 Propose Trade"):
                    if accepted:
                        for name in my_names:
                            st.session_state.my_roster_overrides[name] = partner_team['id']
                        for name in their_names:
                            st.session_state.my_roster_overrides[name] = current_team_id
                        trade_str = (
                            f"Sent: {', '.join(my_names)}  →  "
                            f"Received: {', '.join(their_names)} (from {partner_name})"
                        )
                        st.session_state.trade_history.insert(0, trade_str)
                        save_state()
                        st.success(f"Trade complete! {trade_str}")
                        st.rerun()
                    else:
                        st.error(f"❌ Rejected by {partner_name}'s GM.")

        if st.session_state.trade_history:
            with st.expander("Trade History"):
                for trade in st.session_state.trade_history[:10]:
                    st.write(f"• {trade}")

    # ── STANDINGS ─────────────────────────────────────────────────────────────
    with tab_standings:
        st.subheader("League Standings")
        standings = st.session_state.get('standings', {})
        team_map_by_id = {t['id']: t for t in all_teams}

        if not standings or all(s['w'] + s['l'] == 0 for s in standings.values()):
            st.info("Play some games to see standings.")
        else:
            st.write(f"**Game {games_played} of 82**")
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
                        leader_pct = leader_w / max(leader_w + leader_l, 1)

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

            # Show bracket if playoffs are underway
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
                        # Keep team and roster, reset everything else
                        st.session_state.results = []
                        st.session_state.season_pts = {}
                        st.session_state.injured_list = {}
                        st.session_state.stamina = {}
                        st.session_state.standings = {t['id']: {'w': 0, 'l': 0} for t in all_teams}
                        st.session_state.games_played = 0
                        st.session_state.season_phase = 'regular'
                        st.session_state.playoff_bracket = None
                        st.session_state.current_series = None
                        st.session_state.last_game_result = None
                        st.session_state.batch_results = None
                        save_state()
                        st.rerun()

    # ── SEASON STATS ──────────────────────────────────────────────────────────
    with tab_stats:
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
