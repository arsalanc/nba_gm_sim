import streamlit as st
import pandas as pd
import json
import os
import tempfile
from nba_api.stats.static import teams
from nba_api.stats.endpoints import leagueleaders, playerindex

# --- CONSTANTS ---
# Use temp directory for cloud compatibility (Streamlit Cloud has a read-only working dir)
SAVE_FILE = os.path.join(tempfile.gettempdir(), "gm_save.json")


# --- URL HELPERS ---
def player_img_url(player_id):
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


# --- STAMINA HELPERS ---
def stamina_drain_per_quarter(player_min, tactic='Balanced'):
    """Stamina drain for one quarter based on real MPG.
    1200/MIN → 36 MPG ~33/Q, 24 MPG ~50/Q, 12 MPG ~100/Q."""
    clamped_min = max(player_min, 4)
    base_drain = 1200 / clamped_min
    base_drain = max(15, min(100, base_drain))
    if tactic == 'Grit & Grind':
        base_drain *= 1.3
    elif tactic == 'Pace & Space':
        base_drain *= 1.1
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
    keys = ['my_team_id', 'difficulty', 'results', 'season_pts', 'injured_list',
            'my_roster_overrides', 'trade_history',
            'standings', 'games_played', 'season_phase', 'playoff_bracket',
            'current_series', 'live_game', 'season_stamina', 'trade_cooldown']
    state = {k: st.session_state.get(k) for k in keys}
    with open(SAVE_FILE, 'w') as f:
        json.dump(state, f)

def load_state():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE) as f:
            data = json.load(f)
        # JSON converts int keys to strings — convert standings keys back to int
        if 'standings' in data and isinstance(data['standings'], dict):
            data['standings'] = {int(k): v for k, v in data['standings'].items()}
        for k, v in data.items():
            if k not in st.session_state:
                st.session_state[k] = v


# --- DATA ---
@st.cache_data
def load_nba_data():
    try:
        nba_teams = teams.get_teams()
        raw_data = leagueleaders.LeagueLeaders(season='2025-26', per_mode48='PerGame').get_dict()
        headers = raw_data['resultSet']['headers']
        rows = raw_data['resultSet']['rowSet']
        df = pd.DataFrame(rows, columns=headers)
        df['TEAM_ID'] = df['TEAM_ID'].astype(int)
        df['PLAYER_ID'] = df['PLAYER_ID'].astype(int)
        df['SALARY'] = df['PTS'].apply(estimate_salary)

        # Player positions via PlayerIndex (single call for all active players)
        try:
            pi = playerindex.PlayerIndex(season='2025-26', active_nullable=1)
            pi_df = pi.get_data_frames()[0]
            pos_map = dict(zip(pi_df['PERSON_ID'].astype(int), pi_df['POSITION']))
            df['POSITION'] = df['PLAYER_ID'].map(pos_map)
            # replace empty strings as well as NaN
            df['POSITION'] = df['POSITION'].replace('', None).fillna('?')
        except Exception as e:
            st.warning(f"⚠️ Could not load player positions: {e}")
            df['POSITION'] = '?'

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

        return nba_teams, df
    except Exception as e:
        st.error(f"Data Load Failed: {e}")
        return [], pd.DataFrame(columns=['PLAYER', 'TEAM_ID', 'PTS', 'PLAYER_ID', 'SALARY'])


# --- TRADE EVALUATION ---
def evaluate_trade(my_players_df, their_players_df, difficulty='Easy'):
    """Return (accepted, my_pts, their_pts, my_sal, their_sal)."""
    my_pts = my_players_df['PTS'].sum()
    their_pts = their_players_df['PTS'].sum()
    my_sal = my_players_df['SALARY'].sum()
    their_sal = their_players_df['SALARY'].sum()

    # NBA salary matching: incoming ≤ outgoing * 1.25 + $100K
    salary_ok = their_sal <= my_sal * 1.25 + 100_000
    # AI GM threshold — Hard: won't give up more than 5% better PPG; Easy: 15%
    threshold = 1.05 if difficulty == 'Hard' else 1.15
    value_ok = their_pts <= my_pts * threshold

    return salary_ok and value_ok, my_pts, their_pts, my_sal, their_sal
