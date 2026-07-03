import streamlit as st
import os

from utils import (
    SAVE_FILE, player_img_url, team_logo_url,
    fmt_salary, save_state, load_state, load_nba_data,
    apply_roster_overrides, win_streak,
    salary_cap_for_season, luxury_tax_for_season,
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
    'franchise_mode': True,     # Multi-season: offseason draft + player aging
    'season_number': 1,
    'player_progression': {},   # Franchise: cumulative aging deltas {name: {ovr, mult}}
    'retired_players': [],      # Franchise: names removed from the league
    'rookie_rows': [],          # Franchise: drafted prospects as stat rows
    'draft_state': None,        # Franchise: in-progress draft (order/prospects/picks)
    'offseason_report': None,   # Franchise: retirements + risers/fallers for display
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
             "**Hard:** Opponents play near full strength, injuries are more frequent, "
             "stamina carries over between games, and trades are harder to pull off.",
    )

    season_length_choice = st.radio(
        "Season Length:",
        [20, 41, 82, 0],
        index=2,
        horizontal=True,
        format_func=lambda x: "🏆 Playoffs Only" if x == 0 else f"{x} games",
        help="**20 games:** Quick season, good for testing.\n\n"
             "**41 games:** Half-season, balanced experience.\n\n"
             "**82 games:** Full NBA regular season.\n\n"
             "**Playoffs Only:** we sim the regular season for you — pick a team and "
             "jump straight into the bracket. If your team misses the cut, "
             "they sneak in as the #8 seed.",
    )

    if season_length_choice != 0:
        franchise_choice = st.checkbox(
            "🏛️ **Franchise Mode** — multi-season play with an offseason draft, "
            "player aging, and retirements",
            value=True,
            help="After each championship you enter the offseason: players age and "
                 "retire, then a draft of generated prospects with hidden potential. "
                 "Turn off for a single-season run that resets to the real league.",
        )
    else:
        franchise_choice = False  # Playoffs Only locks rosters — no draft

    if st.button("✍️ Sign Contract"):
        user_id = team_map[selected]
        st.session_state.my_team_id = user_id
        st.session_state.difficulty = diff_choice
        st.session_state.season_length = season_length_choice
        st.session_state.franchise_mode = franchise_choice
        st.session_state.standings = {t['id']: {'w': 0, 'l': 0} for t in all_teams}
        if season_length_choice == 0:
            from engine import setup_playoffs_only
            standings, bracket, series = setup_playoffs_only(all_teams, all_stats, user_id)
            st.session_state.standings = standings
            st.session_state.playoff_bracket = bracket
            st.session_state.current_series = series
            st.session_state.season_phase = 'playoffs_user'
        save_state()
        st.rerun()

# ── GM DASHBOARD ──────────────────────────────────────────────────────────────
else:
    my_team = next(t for t in all_teams if t['id'] == st.session_state.my_team_id)
    current_team_id = int(st.session_state.my_team_id)
    overrides = st.session_state.my_roster_overrides

    # Franchise Mode: replay league evolution (retirements, draftees, aging)
    # onto the freshly loaded data, then apply trades league-wide so traded
    # players actually change teams for opponent rosters, scouting, and sims.
    from offseason import apply_league_evolution
    all_stats = apply_league_evolution(
        all_stats,
        st.session_state.player_progression,
        st.session_state.retired_players,
        st.session_state.rookie_rows,
        st.session_state.season_number,
    )
    all_stats = apply_roster_overrides(all_stats, overrides)
    acquired = [name for name, tid in overrides.items() if tid == current_team_id]
    roster = all_stats[all_stats['TEAM_ID'] == current_team_id].copy()

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
    if st.session_state.get('franchise_mode'):
        _sn = st.session_state.get('season_number', 1)
        st.sidebar.caption(f"🏛️ Season {_sn} · {2024 + _sn}-{(25 + _sn) % 100:02d}")
    diff_badge = "🔴 Hard" if hard else "🟢 Easy"
    if season_phase == 'regular':
        st.sidebar.write(f"**Record:** {w}W — {l}L  ·  Game {games_played}/{season_length}  ·  {diff_badge}")
    elif season_phase in ('playoffs_user', 'playoffs_spectate'):
        st.sidebar.write(f"**Record:** {w}W — {l}L  ·  Playoffs  ·  {diff_badge}")
    else:
        st.sidebar.write(f"**Record:** {w}W — {l}L  ·  {diff_badge}")

    _streak = win_streak(st.session_state.results)
    if _streak >= 3:
        st.sidebar.success(f"🔥 {_streak}-game win streak — momentum +{min(_streak, 5)}% scoring")

    # Salary cap
    st.sidebar.divider()
    st.sidebar.subheader("💰 Salary Cap")
    # Cap and tax lines grow 8%/season in Franchise Mode, like the real NBA —
    # developing rosters get more expensive, but the league gets richer too.
    _sn = st.session_state.get('season_number', 1)
    cap_line = salary_cap_for_season(_sn)
    tax_line = luxury_tax_for_season(_sn)
    roster_salary = roster['SALARY'].sum()
    cap_pct = min(roster_salary / cap_line, 1.2)
    if roster_salary > tax_line:
        st.sidebar.error(f"{fmt_salary(roster_salary)} / {fmt_salary(cap_line)} — Over Luxury Tax!")
        st.sidebar.caption("🚨 **Apron rules:** trade salary matching tightened to 110% "
                           f"(tax line: {fmt_salary(tax_line)})")
    elif roster_salary > cap_line:
        st.sidebar.warning(f"{fmt_salary(roster_salary)} / {fmt_salary(cap_line)} — Over Cap")
        st.sidebar.caption(f"Soft cap — no penalty until the luxury tax at {fmt_salary(tax_line)}")
    else:
        st.sidebar.success(f"{fmt_salary(roster_salary)} / {fmt_salary(cap_line)}")
    st.sidebar.progress(min(cap_pct, 1.0))
    st.sidebar.caption(f"Cap space: {fmt_salary(max(0, cap_line - roster_salary))}")

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

    # ── DRAFT ROOM (Franchise Mode offseason takes over the main area) ────────
    if season_phase == 'draft':
        from tabs.draft import render as render_draft
        render_draft(my_team, current_team_id, all_teams)
        st.stop()

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
        render_trade_desk(my_team, current_team_id, roster, all_teams, all_stats, acquired, difficulty, hard,
                          games_played, season_phase, season_length)

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
        render_season_stats(all_stats, w, l, all_teams, roster, my_team)

    # ── HOW TO PLAY ───────────────────────────────────────────────────────────
    with tab_howto:
        from tabs.how_to_play import render as render_how_to_play
        render_how_to_play()
