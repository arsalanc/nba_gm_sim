import streamlit as st
import pandas as pd
import os

from utils import (
    SAVE_FILE, SALARY_CAP, LUXURY_TAX, player_img_url, team_logo_url,
    fmt_salary, save_state, load_state, load_nba_data,
)

# ─── APP ──────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="NBA GM Sim", layout="wide")
st.title("🏀 NBA GM Simulator")

load_state()
all_teams, all_stats = load_nba_data()

# Default session state (skipped if already loaded from save)
_defaults = {
    'my_team_id': None,
    'difficulty': 'Easy',
    'season_length': 82,
    'results': [],
    'season_pts': {},
    'injured_list': {},
    'my_roster_overrides': {},
    'trade_history': [],
    'standings': {},
    'games_played': 0,
    'season_phase': 'regular',
    'playoff_bracket': None,
    'current_series': None,
    'live_game': None,
    'season_stamina': {},       # Hard mode: per-player stamina carryover between games
    'trade_cooldown': 0,        # Hard mode: games remaining with chemistry penalty
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

    diff_choice = st.radio(
        "Difficulty:",
        ["Easy", "Hard"],
        horizontal=True,
        help="**Easy:** Relaxed sim, opponents are inconsistent. Great for casual play.\n\n"
             "**Hard:** Opponents play at full strength, tactic advantages are removed, "
             "injuries are more frequent, stamina carries over between games, and trades are harder to pull off.",
    )

    season_length_choice = st.radio(
        "Season Length:",
        [20, 41, 82],
        index=2,
        horizontal=True,
        format_func=lambda x: f"{x} games",
        help="**20 games:** Quick season, good for testing.\n\n"
             "**41 games:** Half-season, balanced experience.\n\n"
             "**82 games:** Full NBA regular season.",
    )

    if st.button("✍️ Sign Contract"):
        st.session_state.my_team_id = team_map[selected]
        st.session_state.difficulty = diff_choice
        st.session_state.season_length = season_length_choice
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
    difficulty = st.session_state.get('difficulty', 'Easy')
    season_length = st.session_state.get('season_length', 82)
    hard = difficulty == 'Hard'

    st.sidebar.header(my_team['full_name'])
    diff_badge = "🔴 Hard" if hard else "🟢 Easy"
    if season_phase == 'regular':
        st.sidebar.write(f"**Record:** {w}W — {l}L  ·  Game {games_played}/{season_length}  ·  {diff_badge}")
    elif season_phase in ('playoffs_user', 'playoffs_spectate'):
        st.sidebar.write(f"**Record:** {w}W — {l}L  ·  Playoffs  ·  {diff_badge}")
    else:
        st.sidebar.write(f"**Record:** {w}W — {l}L  ·  {diff_badge}")

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

    if hard and st.session_state.get('trade_cooldown', 0) > 0:
        st.sidebar.divider()
        st.sidebar.warning(f"⚠️ Chemistry disruption: **{st.session_state.trade_cooldown}** games left "
                           f"(-5% scoring)")

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
    _available = _healthy.head(10)
    _suggested = _available.nlargest(5, 'PTS')['PLAYER'].tolist()
    st.session_state.current_starters = [
        row['PLAYER'] for _, row in _available.iterrows()
        if st.session_state.get(f"starter_{row['PLAYER']}", row['PLAYER'] in _suggested)
    ]

    # ── MAIN TABS ─────────────────────────────────────────────────────────────
    tab_gameplan, tab_game, tab_trade, tab_standings, tab_bracket, tab_stats, tab_howto = st.tabs(
        ["📝 Gameplan", "🏟️ Game Day", "📋 Trade Desk", "🏆 Standings", "🏀 Bracket", "📊 Season Stats", "❓ How to Play"]
    )

    # ── GAMEPLAN ──────────────────────────────────────────────────────────────
    with tab_gameplan:
        from tabs.gameplan import render as render_gameplan
        render_gameplan(my_team, current_team_id, roster, all_teams, all_stats, season_phase, games_played, season_length)

    # ── GAME DAY ──────────────────────────────────────────────────────────────
    with tab_game:
        from tabs.game_day import render as render_game_day
        render_game_day(my_team, current_team_id, roster, all_teams, all_stats,
                        season_phase, games_played, difficulty, hard, season_length)


    # ── TRADE DESK ────────────────────────────────────────────────────────────
    with tab_trade:
        from tabs.trade_desk import render as render_trade_desk
        render_trade_desk(my_team, current_team_id, roster, all_teams, all_stats, acquired, difficulty, hard)

    # ── STANDINGS ─────────────────────────────────────────────────────────────
    with tab_standings:
        from tabs.standings import render as render_standings
        render_standings(my_team, current_team_id, all_teams, all_stats, games_played, season_phase, season_length)

    # ── PLAYOFF BRACKET ──────────────────────────────────────────────────────
    with tab_bracket:
        from tabs.bracket import render as render_bracket
        render_bracket(current_team_id, all_teams)


    # ── SEASON STATS ──────────────────────────────────────────────────────────
    with tab_stats:
        from tabs.season_stats import render as render_season_stats
        render_season_stats(all_stats, w, l)

    # ── HOW TO PLAY ───────────────────────────────────────────────────────────
    with tab_howto:
        from tabs.how_to_play import render as render_how_to_play
        render_how_to_play()
