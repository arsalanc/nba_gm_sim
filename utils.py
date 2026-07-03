import streamlit as st
import pandas as pd
# import json  # Re-enable if restoring file persistence in save_state/load_state
import os
import tempfile
from nba_api.stats.static import teams
from nba_api.stats.endpoints import leagueleaders, playerindex

# --- CONSTANTS ---
# Use temp directory for cloud compatibility (Streamlit Cloud has a read-only working dir)
SAVE_FILE = os.path.join(tempfile.gettempdir(), "gm_save.json")

SALARY_CAP = 140_700_000
LUXURY_TAX = 170_814_000
CAP_GROWTH = 1.08  # per-season cap growth (Franchise Mode), mirroring real NBA rises


def salary_cap_for_season(season_number=1):
    return int(SALARY_CAP * CAP_GROWTH ** (max(season_number, 1) - 1))


def luxury_tax_for_season(season_number=1):
    return int(LUXURY_TAX * CAP_GROWTH ** (max(season_number, 1) - 1))


# --- URL HELPERS ---
def player_img_url(player_id):
    # Generated draft prospects have synthetic IDs with no NBA headshot —
    # show a generic rookie avatar instead of a broken image.
    if player_id >= 90_000_000:
        return "https://ui-avatars.com/api/?name=R&background=17408B&color=ffffff&size=190&bold=true"
    return f"https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"

def team_logo_url(team_id):
    return f"https://cdn.nba.com/logos/nba/{team_id}/global/L/logo.svg"


# --- CONFERENCE DATA ---
CONFERENCE = {
    1610612737: 'East',  # ATL
    1610612738: 'East',  # BOS
    1610612739: 'East',  # CLE
    1610612740: 'West',  # NOP
    1610612741: 'East',  # CHI
    1610612742: 'West',  # DAL
    1610612743: 'West',  # DEN
    1610612744: 'West',  # GSW
    1610612745: 'West',  # HOU
    1610612746: 'West',  # LAC
    1610612747: 'West',  # LAL
    1610612748: 'East',  # MIA
    1610612749: 'East',  # MIL
    1610612750: 'West',  # MIN
    1610612751: 'East',  # BKN
    1610612752: 'East',  # NYK
    1610612753: 'East',  # ORL
    1610612754: 'East',  # IND
    1610612755: 'East',  # PHI
    1610612756: 'West',  # PHX
    1610612757: 'West',  # POR
    1610612758: 'West',  # SAC
    1610612759: 'West',  # SAS
    1610612760: 'West',  # OKC
    1610612761: 'East',  # TOR
    1610612762: 'West',  # UTA
    1610612763: 'West',  # MEM
    1610612764: 'East',  # WAS
    1610612765: 'East',  # DET
    1610612766: 'East',  # CHA
}


def compute_team_strength(team_id, all_stats):
    """Average OVERALL of top 8 players on a team."""
    team_df = all_stats[all_stats['TEAM_ID'] == team_id]
    top8 = team_df.nlargest(8, 'OVERALL')
    return top8['OVERALL'].mean() if not top8.empty else 70


def get_win_probability(strength_a, strength_b):
    """Logistic win probability for team A given both strengths."""
    diff = strength_a - strength_b
    return 1 / (1 + 10 ** (-diff / 15))


# --- TACTICS ---
# Tactics trade pace for variance rather than offering a free stat boost:
#   Pace & Space — more possessions, higher scores, *steadier* outcomes. The
#                  favorite's pick: over more possessions, talent wins out.
#   Grit & Grind — slow, physical, low-scoring with *wild* swings. The
#                  underdog's pick: shorten the game and anything can happen.
# 'own'/'opp' scale quick-sim totals, 'spread' is the per-player performance
# range (±), 'drain' is quick-sim stamina cost, 'live_possessions' is
# per-team possessions per quarter in live games.
TACTICS = {
    'Balanced': dict(
        own=1.00, opp=1.00, spread=0.20, drain=15,
        live_possessions=24, three_boost=1.0,
        blurb="Normal pace, no modifiers — let the rosters decide.",
    ),
    'Pace & Space': dict(
        own=1.10, opp=1.10, spread=0.13, drain=19,
        live_possessions=27, three_boost=1.3,
        blurb="Up-tempo: higher scores, steadier outcomes — the favorite's pick. "
              "Drains stamina faster.",
    ),
    'Grit & Grind': dict(
        own=0.85, opp=0.85, spread=0.30, drain=17,
        live_possessions=20, three_boost=0.85,
        blurb="Slow it down: low-scoring rock fights with wild swings — the underdog's pick.",
    ),
}


def apply_roster_overrides(all_stats, overrides):
    """Return a copy of all_stats with traded players moved to their new teams.
    Ensures trades affect opponent rosters, scouting, and league sims — not just
    the user's own roster view."""
    if not overrides:
        return all_stats
    df = all_stats.copy()
    for name, tid in overrides.items():
        df.loc[df['PLAYER'] == name, 'TEAM_ID'] = int(tid)
    return df


def win_streak(results):
    """Length of the current trailing win streak."""
    streak = 0
    for r in reversed(results):
        if r != 'W':
            break
        streak += 1
    return streak


def momentum_boost(results):
    """1.00–1.05 scoring multiplier: teams on a 3+ game win streak play with
    confidence (+1% per streak game, capped at +5%)."""
    s = win_streak(results)
    return 1.0 + min(s, 5) * 0.01 if s >= 3 else 1.0


# Home court is worth roughly ±2% in the NBA. None = neutral (no modifier).
def home_court_factor(is_home):
    if is_home is True:
        return 1.02
    if is_home is False:
        return 0.98
    return 1.0


def lineup_defense_factor(lineup_df):
    """Multiplier applied to opponent quick-sim score based on the starters'
    combined steals + blocks. ~7 stocks is league-average for a starting five;
    an elite defensive five suppresses opponent scoring by up to ~10%."""
    if 'STL' not in lineup_df.columns or 'BLK' not in lineup_df.columns or lineup_df.empty:
        return 1.0
    stocks = float(lineup_df['STL'].sum() + lineup_df['BLK'].sum())
    return max(0.90, min(1.08, 1.0 - (stocks - 7.0) * 0.015))


# --- STAMINA HELPERS ---
def stamina_drain_per_quarter(player_min, tactic='Balanced'):
    """Stamina drain for one quarter based on real MPG.
    1200/MIN → 36 MPG ~33/Q, 24 MPG ~50/Q, 12 MPG ~100/Q."""
    clamped_min = max(player_min, 4)
    base_drain = 1200 / clamped_min
    base_drain = max(15, min(100, base_drain))
    if tactic == 'Grit & Grind':
        base_drain *= 1.15   # physical, but the slow pace limits total wear
    elif tactic == 'Pace & Space':
        base_drain *= 1.25   # running costs legs
    return base_drain


def stamina_performance_modifier(stamina):
    """Returns 0.4–1.0 multiplier based on current stamina."""
    if stamina >= 70:
        return 1.0
    elif stamina >= 40:
        return 0.7 + (stamina - 40) * 0.01
    else:
        return max(0.4, 0.4 + stamina * 0.0075)


# --- SALARY / FORMATTING ---
def estimate_salary(pts):
    if pts >= 25: return 35_000_000
    elif pts >= 20: return 25_000_000
    elif pts >= 15: return 18_000_000
    elif pts >= 10: return 10_000_000
    else: return 5_000_000

def fmt_salary(s):
    return f"${s / 1_000_000:.1f}M"

def overall_badge(ovr):
    """Return a colored label string for an overall rating."""
    if ovr >= 90: return f"🔴 {ovr}"
    if ovr >= 80: return f"🟠 {ovr}"
    if ovr >= 70: return f"🟡 {ovr}"
    return f"⚪ {ovr}"


# --- PERSISTENCE ---
def save_state():
    pass  # File persistence disabled — each session is isolated (safe for multi-user cloud hosting)
    # keys = ['my_team_id', 'difficulty', 'results', 'season_pts', 'injured_list',
    #         'my_roster_overrides', 'trade_history',
    #         'standings', 'games_played', 'season_phase', 'playoff_bracket',
    #         'current_series', 'live_game', 'season_stamina', 'trade_cooldown']
    # state = {k: st.session_state.get(k) for k in keys}
    # with open(SAVE_FILE, 'w') as f:
    #     json.dump(state, f)

def load_state():
    pass  # File persistence disabled — each session is isolated (safe for multi-user cloud hosting)
    # if os.path.exists(SAVE_FILE):
    #     with open(SAVE_FILE) as f:
    #         data = json.load(f)
    #     # JSON converts int keys to strings — convert standings keys back to int
    #     if 'standings' in data and isinstance(data['standings'], dict):
    #         data['standings'] = {int(k): v for k, v in data['standings'].items()}
    #     for k, v in data.items():
    #         if k not in st.session_state:
    #             st.session_state[k] = v


# --- DATA ---
# Bundled snapshot for hosts that can't reach stats.nba.com (the NBA blocks
# datacenter IPs, which includes Streamlit Cloud). Regenerate with:
#   python make_snapshot.py
SNAPSHOT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nba_snapshot.csv")


def fetch_live_nba_stats(timeout=10):
    """Fetch and fully process current league data from stats.nba.com.
    Raises on network failure — callers decide the fallback."""
    raw_data = leagueleaders.LeagueLeaders(
        season='2025-26', per_mode48='PerGame', timeout=timeout
    ).get_dict()
    headers = raw_data['resultSet']['headers']
    rows = raw_data['resultSet']['rowSet']
    df = pd.DataFrame(rows, columns=headers)
    df['TEAM_ID'] = df['TEAM_ID'].astype(int)
    df['PLAYER_ID'] = df['PLAYER_ID'].astype(int)
    df['SALARY'] = df['PTS'].apply(estimate_salary)

    # Player positions via PlayerIndex (single call for all active players)
    try:
        pi = playerindex.PlayerIndex(season='2025-26', active_nullable=1, timeout=timeout)
        pi_df = pi.get_data_frames()[0]
        pos_map = dict(zip(pi_df['PERSON_ID'].astype(int), pi_df['POSITION']))
        df['POSITION'] = df['PLAYER_ID'].map(pos_map)
        # replace empty strings as well as NaN
        df['POSITION'] = df['POSITION'].replace('', None).fillna('?')

        # Age estimate for Franchise Mode aging: ~21 at draft/debut year.
        # (2026 = current 2025-26 season; rough is fine for a growth curve.)
        draft_yr = pd.to_numeric(pi_df.get('DRAFT_YEAR'), errors='coerce')
        from_yr = pd.to_numeric(pi_df.get('FROM_YEAR'), errors='coerce')
        start_yr = draft_yr.fillna(from_yr)
        age_est = (2026 - start_yr + 21).clip(19, 44)
        age_map = dict(zip(pi_df['PERSON_ID'].astype(int), age_est))
        df['AGE'] = df['PLAYER_ID'].map(age_map).fillna(27).astype(int)
    except Exception:
        df['POSITION'] = '?'
        df['AGE'] = 27

    # Overall rating: NBA efficiency formula normalised to 60-99
    eff_cols = ['PTS', 'REB', 'AST', 'STL', 'BLK', 'FGA', 'FGM', 'FTA', 'FTM', 'TOV']
    if all(c in df.columns for c in eff_cols):
        df['_EFF'] = (
            df['PTS'] + df['REB'] + df['AST'] + df['STL'] + df['BLK']
            - (df['FGA'] - df['FGM']) - (df['FTA'] - df['FTM']) - df['TOV']
        )
    else:
        df['_EFF'] = df['PTS']   # fallback
    eff_min, eff_max = df['_EFF'].min(), df['_EFF'].max()
    df['OVERALL'] = (
        (df['_EFF'] - eff_min) / (eff_max - eff_min) * 39 + 60
    ).clip(60, 99).astype(int)
    df.drop(columns=['_EFF'], inplace=True)
    return df


@st.cache_data
def load_nba_data():
    """Returns (teams, stats_df, source). source is 'live' or 'snapshot'.
    Team list is a static offline table; only the stats need the network."""
    nba_teams = teams.get_teams()
    try:
        return nba_teams, fetch_live_nba_stats(), 'live'
    except Exception as e:
        if os.path.exists(SNAPSHOT_FILE):
            df = pd.read_csv(SNAPSHOT_FILE)
            df['TEAM_ID'] = df['TEAM_ID'].astype(int)
            df['PLAYER_ID'] = df['PLAYER_ID'].astype(int)
            return nba_teams, df, 'snapshot'
        st.error(f"Data Load Failed (and no bundled snapshot found): {e}")
        return [], pd.DataFrame(columns=['PLAYER', 'TEAM_ID', 'PTS', 'PLAYER_ID', 'SALARY']), 'none'


# --- TRADE EVALUATION ---
def trade_value(players_df):
    """Superlinear trade value from OVERALL — stars are worth far more than
    the sum of equivalent role players, so you can't package three scrubs
    for a superstar. OVR 90 ≈ value of three OVR 75 players combined."""
    if 'OVERALL' in players_df.columns and not players_df.empty:
        return float(((players_df['OVERALL'] - 55).clip(lower=1) ** 1.7).sum())
    return float(players_df['PTS'].sum() * 10)  # fallback


def evaluate_trade(my_players_df, their_players_df, difficulty='Easy', match_factor=1.25):
    """Return (accepted, my_value, their_value, my_sal, their_sal).
    match_factor tightens to 1.10 under luxury-tax apron rules."""
    my_val = trade_value(my_players_df)
    their_val = trade_value(their_players_df)
    my_sal = my_players_df['SALARY'].sum()
    their_sal = their_players_df['SALARY'].sum()

    # NBA salary matching: incoming ≤ outgoing * match_factor + $100K
    salary_ok = their_sal <= my_sal * match_factor + 100_000
    # AI GM threshold — Hard: demands near-even value; Easy: accepts a 10% haircut
    threshold = 1.02 if difficulty == 'Hard' else 1.10
    value_ok = their_val <= my_val * threshold

    return salary_ok and value_ok, my_val, their_val, my_sal, their_sal
