import streamlit as st
import random
from utils import (
    compute_team_strength, get_win_probability, CONFERENCE,
    stamina_drain_per_quarter, stamina_performance_modifier,
    TACTICS, lineup_defense_factor, momentum_boost, home_court_factor,
)


def simulate_game(lineup_df, roster_df, tactic, all_stats, all_teams, my_team_id, rested_players,
                  opponent_team_id=None, difficulty='Easy', is_playoffs=False, is_home=None):
    hard = difficulty == 'Hard'
    t = TACTICS.get(tactic, TACTICS['Balanced'])
    spread = t['spread']
    box_score = []
    total_score = 0
    injury_reports = []
    sub_reports = []

    # Use pre-determined opponent if provided
    if opponent_team_id is not None:
        opp_team = next((t for t in all_teams if t['id'] == opponent_team_id), None)
    if opponent_team_id is None or opp_team is None:
        opp_team = random.choice([t for t in all_teams if t['id'] != my_team_id])
    opp_team_name = opp_team['full_name']
    opp_roster = all_stats[all_stats['TEAM_ID'] == opp_team['id']]
    opp_top5 = opp_roster.nlargest(5, 'PTS')
    opp_bench_df = opp_roster[~opp_roster['PLAYER'].isin(opp_top5['PLAYER'])].nlargest(5, 'PTS')

    opp_score = 0
    opp_box_score = []
    # Opponent intensity: Hard plays near full strength (even matchups are true
    # coin-flips), Easy keeps you favored without being a total pushover so the
    # standings race still matters. Playoffs raise the floor — everyone locks in.
    if hard:
        stam_floor = 95 if is_playoffs else 90
    else:
        stam_floor = 86 if is_playoffs else 80
    for _, opp_player in opp_top5.iterrows():
        opp_stam = random.randint(stam_floor, 100)
        opp_pts = int(opp_player['PTS'] * random.uniform(1 - spread, 1 + spread) * (opp_stam / 100))

        # Opponent injury / foul-out — sub in bench player
        opp_inj_chance = 0.03 + ((100 - opp_stam) / 500)
        if random.random() < opp_inj_chance and not opp_bench_df.empty:
            opp_pts = int(opp_pts * 0.2)
            sub_row = opp_bench_df.iloc[0]
            sub_stam = random.randint(70, 100)
            opp_pts += int(sub_row['PTS'] * random.uniform(0.7, 1.0) * (sub_stam / 100) * 0.7)
            injury_reports.append(
                f"🚨 {opp_player['PLAYER']} ({opp_team_name}) left the game!"
            )
            opp_bench_df = opp_bench_df.iloc[1:]  # remove used sub

        opp_score += opp_pts
        opp_box_score.append({
            "Player": opp_player['PLAYER'],
            "PLAYER_ID": int(opp_player['PLAYER_ID']),
            "PTS": opp_pts,
            "REB": int(opp_player.get('REB', 0) * random.uniform(0.7, 1.3)),
            "AST": int(opp_player.get('AST', 0) * random.uniform(0.7, 1.3)),
            "STL": int(opp_player.get('STL', 0) * random.uniform(0.5, 1.5)),
            "BLK": int(opp_player.get('BLK', 0) * random.uniform(0.5, 1.5)),
            "TOV": int(opp_player.get('TOV', 0) * random.uniform(0.7, 1.3)),
            "Stamina Left": opp_stam,
        })

    # Bench contribution: Hard = scaled by actual bench quality; Easy = flat random
    if hard:
        opp_remaining = opp_roster[~opp_roster['PLAYER'].isin(opp_top5['PLAYER'])]
        opp_bench_avg = opp_remaining['PTS'].mean() if not opp_remaining.empty else 5
        opp_bench_contribution = int(opp_bench_avg * random.uniform(2.5, 4.0))
    else:
        opp_bench_contribution = random.randint(30, 45)
    opp_score += opp_bench_contribution
    opp_box_score.append({
        "Player": "Bench / Role Players",
        "PLAYER_ID": 0,
        "PTS": opp_bench_contribution,
        "REB": 0, "AST": 0, "STL": 0, "BLK": 0, "TOV": 0,
        "Stamina Left": 100,
    })

    starter_names = lineup_df['PLAYER'].tolist()
    injured_names = list(st.session_state.injured_list.keys())
    drain = t['drain']

    # Build bench pool sorted by PTS
    bench_df = roster_df[
        ~roster_df['PLAYER'].isin(starter_names + injured_names + rested_players)
    ].sort_values('PTS', ascending=False)
    bench_pool = bench_df.to_dict('records')

    # Internal stamina — Hard mode reads carryover; Easy always 100
    season_stam = st.session_state.get('season_stamina', {}) if hard else {}
    game_stamina = {}
    for name in starter_names:
        game_stamina[name] = season_stam.get(name, 100)
    for rec in bench_pool:
        game_stamina[rec['PLAYER']] = season_stam.get(rec['PLAYER'], 100)

    # Hard mode: trade chemistry penalty
    chem_penalty = 0.95 if hard and st.session_state.get('trade_cooldown', 0) > 0 else 1.0

    for _, player in lineup_df.iterrows():
        name = player['PLAYER']
        pid = int(player['PLAYER_ID'])
        current_stam = game_stamina.get(name, 100)

        # Sub out if stamina critically low
        if current_stam < 30 and bench_pool:
            sub = bench_pool.pop(0)
            sub_name = sub['PLAYER']
            sub_stam = game_stamina.get(sub_name, 100)
            sub_pts = int(sub['PTS'] * random.uniform(0.7, 1.1) * (sub_stam / 100) * 0.7 * chem_penalty)
            new_sub_stam = max(0, sub_stam - 10)
            game_stamina[sub_name] = new_sub_stam
            total_score += sub_pts
            box_score.append({
                "Player": f"↔ {sub_name} (sub for {name.split()[-1]})",
                "PLAYER_ID": int(sub['PLAYER_ID']),
                "PTS": sub_pts, "REB": 0, "AST": 0, "STL": 0, "BLK": 0, "TOV": 0,
                "Stamina Left": new_sub_stam,
            })
            sub_reports.append(f"↔ {sub_name} subbed in for {name}")
            box_score.append({
                "Player": name,
                "PLAYER_ID": pid,
                "PTS": 0, "REB": 0, "AST": 0, "STL": 0, "BLK": 0, "TOV": 0,
                "Stamina Left": current_stam,
            })
            continue

        fatigue_multiplier = current_stam / 100
        pts = int(player['PTS'] * random.uniform(1 - spread, 1 + spread) * fatigue_multiplier * chem_penalty)

        # Tiered injury check — Hard: more frequent and severe
        if hard:
            injury_chance = 0.05 + ((100 - current_stam) / 350)
        else:
            injury_chance = 0.03 + ((100 - current_stam) / 500)
        if random.random() < injury_chance and name not in st.session_state.injured_list:
            pts = int(pts * 0.2)
            severity = random.random()
            if hard:
                # Harder injuries: minor < 0.35, moderate < 0.7, severe >= 0.7
                if severity < 0.35:
                    duration, tier = random.randint(1, 3), "MINOR"
                elif severity < 0.70:
                    duration, tier = random.randint(3, 8), "MODERATE"
                else:
                    duration, tier = random.randint(8, 20), "SEVERE"
            else:
                if severity < 0.6:
                    duration, tier = random.randint(1, 2), "MINOR"
                elif severity < 0.9:
                    duration, tier = random.randint(3, 6), "MODERATE"
                else:
                    duration, tier = random.randint(8, 15), "SEVERE"
            st.session_state.injured_list[name] = duration
            injury_reports.append(
                f"🚨 {name} — {tier} injury, OUT {duration} game{'s' if duration > 1 else ''}!"
            )

        new_stam = max(0, current_stam - drain)
        game_stamina[name] = new_stam
        total_score += pts
        p_row = lineup_df[lineup_df['PLAYER'] == name].iloc[0] if name in lineup_df['PLAYER'].values else None
        box_score.append({
            "Player": name,
            "PLAYER_ID": pid,
            "PTS": pts,
            "REB": int(p_row['REB'] * random.uniform(0.7, 1.3)) if p_row is not None and 'REB' in p_row else 0,
            "AST": int(p_row['AST'] * random.uniform(0.7, 1.3)) if p_row is not None and 'AST' in p_row else 0,
            "STL": int(p_row['STL'] * random.uniform(0.5, 1.5)) if p_row is not None and 'STL' in p_row else 0,
            "BLK": int(p_row['BLK'] * random.uniform(0.5, 1.5)) if p_row is not None and 'BLK' in p_row else 0,
            "TOV": int(p_row['TOV'] * random.uniform(0.7, 1.3)) if p_row is not None and 'TOV' in p_row else 0,
            "Stamina Left": new_stam,
        })

    # Bench contribution: Hard = scaled by actual bench quality; Easy = flat
    if hard:
        user_bench_remaining = roster_df[
            ~roster_df['PLAYER'].isin(starter_names + injured_names)
        ]
        user_bench_avg = user_bench_remaining['PTS'].mean() if not user_bench_remaining.empty else 5
        bench_contribution = int(user_bench_avg * random.uniform(2.5, 4.0) * chem_penalty)
    else:
        bench_contribution = random.randint(30, 45)
    total_score += bench_contribution
    box_score.append({
        "Player": "Bench / Role Players",
        "PLAYER_ID": 0,
        "PTS": bench_contribution, "REB": 0, "AST": 0, "STL": 0, "BLK": 0, "TOV": 0,
        "Stamina Left": 100,
    })

    # Hard mode: record end-of-game stamina for carryover
    if hard:
        new_season_stam = dict(st.session_state.get('season_stamina', {}))
        for name, stam in game_stamina.items():
            # Starters recover partially; bench players who didn't play recover fully
            if name in starter_names:
                new_season_stam[name] = min(100, max(stam + 15, 70))
            else:
                new_season_stam[name] = min(100, new_season_stam.get(name, 100) + 25)
        # Load management: rested players sit the whole game and recover fully.
        for name in rested_players:
            new_season_stam[name] = 100
        st.session_state.season_stamina = new_season_stam

    # Apply tactic pace multipliers and the lineup's defensive impact.
    # Defense matters: a starting five with more steals + blocks suppresses
    # the opponent's total (see lineup_defense_factor).
    # Home court is worth ±2%; a 3+ game win streak adds up to +5% momentum.
    total_score = int(total_score * t['own']
                      * home_court_factor(is_home)
                      * momentum_boost(st.session_state.get('results', [])))
    opp_score = int(opp_score * t['opp'] * lineup_defense_factor(lineup_df))

    # Overtime: if tied, play OT periods until someone leads
    ot_period = 1
    while total_score == opp_score:
        ot_pts = random.randint(8, 16)
        ot_opp = random.randint(8, 16)
        if ot_pts != ot_opp:
            total_score += ot_pts
            opp_score += ot_opp
        ot_period += 1
        if ot_period > 5:  # safety cap: force a winner after 5 OTs
            total_score += 1
            break

    # Quick-sim has no possession-level on/off tracking, so approximate +/-:
    # anchor every player to the final team margin, then nudge by how their
    # scoring compared to the lineup average (and a little game-context noise).
    _assign_quick_pm(box_score, total_score - opp_score)
    _assign_quick_pm(opp_box_score, opp_score - total_score)

    return total_score, opp_score, box_score, injury_reports, sub_reports, opp_team_name, opp_box_score


def _assign_quick_pm(box, margin):
    """Approximate a nba.com-style +/- for a quick-sim box score in place."""
    real = [r for r in box if int(r['PLAYER_ID']) != 0]
    avg_pts = sum(r['PTS'] for r in real) / len(real) if real else 0
    for r in box:
        if int(r['PLAYER_ID']) == 0:
            r['PM'] = None  # aggregate bench row — +/- isn't meaningful
        else:
            swing = (r['PTS'] - avg_pts) * 0.5 + random.uniform(-3, 3)
            r['PM'] = margin + int(round(swing))


def post_game_updates(starter_names, rested_players, roster_df):
    """Tick down injury and trade cooldown counters after a game."""
    # Decrement first, then remove fully-recovered players
    for p in list(st.session_state.injured_list.keys()):
        st.session_state.injured_list[p] -= 1
    healed = [p for p, g in st.session_state.injured_list.items() if g <= 0]
    for p in healed:
        del st.session_state.injured_list[p]
    # Trade chemistry cooldown
    if st.session_state.get('trade_cooldown', 0) > 0:
        st.session_state.trade_cooldown -= 1


def generate_next_opponent(my_team_id, all_teams):
    other_teams = [t for t in all_teams if t['id'] != my_team_id]
    return random.choice(other_teams)['id']


def generate_round_matchups(all_teams, round_number):
    """Deterministic matchups for a given round — every team plays exactly once."""
    team_ids = sorted([t['id'] for t in all_teams])
    rng = random.Random(round_number * 7 + 42)
    rng.shuffle(team_ids)
    return [(team_ids[i], team_ids[i + 1]) for i in range(0, len(team_ids), 2)]


def find_user_matchup(matchups, user_team_id):
    """Return (opponent_id, matchup_tuple) for the user's team in this round."""
    for a, b in matchups:
        if a == user_team_id:
            return b, (a, b)
        if b == user_team_id:
            return a, (a, b)
    return None, None


def simulate_other_games(matchups, user_team_id, all_stats):
    """Sim non-user matchups. Returns {team_id: 'W' or 'L'} for all non-user teams."""
    results = {}
    for a, b in matchups:
        if a == user_team_id or b == user_team_id:
            continue
        str_a = compute_team_strength(a, all_stats)
        str_b = compute_team_strength(b, all_stats)
        prob_a = get_win_probability(str_a, str_b)
        if random.random() < prob_a:
            results[a] = 'W'
            results[b] = 'L'
        else:
            results[a] = 'L'
            results[b] = 'W'
    return results


def update_standings(standings, game_results):
    """Increment W/L for each team in game_results dict."""
    for team_id, result in game_results.items():
        if team_id not in standings:
            standings[team_id] = {'w': 0, 'l': 0}
        if result == 'W':
            standings[team_id]['w'] += 1
        else:
            standings[team_id]['l'] += 1


def auto_select_lineup(roster_df, injured_list):
    """Pick best 5 healthy players by PTS for batch sim."""
    injured_names = list(injured_list.keys())
    healthy = roster_df[~roster_df['PLAYER'].isin(injured_names)].copy()
    top5 = healthy.nlargest(5, 'PTS')
    return top5, []


def simulate_playoff_series(team_a_id, team_b_id, all_stats):
    """Simulate a best-of-7 series. Returns (winner_id, wins_a, wins_b)."""
    str_a = compute_team_strength(team_a_id, all_stats)
    str_b = compute_team_strength(team_b_id, all_stats)
    # Higher seed (team_a) gets small home-court edge
    base_prob = get_win_probability(str_a, str_b)
    wins_a, wins_b = 0, 0
    while wins_a < 4 and wins_b < 4:
        # Home court: games 1,2,5,7 for team_a; 3,4,6 for team_b
        game_num = wins_a + wins_b + 1
        home_a = game_num in (1, 2, 5, 7)
        prob = min(base_prob + (0.03 if home_a else -0.03), 0.95)
        if random.random() < prob:
            wins_a += 1
        else:
            wins_b += 1
    winner = team_a_id if wins_a == 4 else team_b_id
    return winner, wins_a, wins_b


def setup_playoffs_only(all_teams, all_stats, user_team_id, games=82):
    """Playoffs Only mode: sim a full regular season league-wide, guarantee the
    user a playoff berth, and return (standings, bracket, user_series)."""
    standings = {t['id']: {'w': 0, 'l': 0} for t in all_teams}
    for rnd in range(games):
        matchups = generate_round_matchups(all_teams, rnd)
        # user_team_id=None so every matchup (including the user's team) is simmed
        results = simulate_other_games(matchups, None, all_stats)
        update_standings(standings, results)

    # Guarantee the berth: if the user missed the top 8, they take the #8 seed's
    # record (an honest underdog run beats a dead-on-arrival mode).
    conf = CONFERENCE.get(user_team_id, 'East')
    conf_teams = [tid for tid in standings if CONFERENCE.get(tid) == conf]
    conf_teams.sort(
        key=lambda t: (
            standings[t]['w'] / max(standings[t]['w'] + standings[t]['l'], 1),
            standings[t]['w'],
        ),
        reverse=True,
    )
    if user_team_id in conf_teams[8:]:
        eighth = conf_teams[7]
        standings[user_team_id], standings[eighth] = standings[eighth], standings[user_team_id]

    bracket = generate_playoff_bracket(standings, all_teams)
    series = None
    for matchup in bracket[conf]['round1']:
        if user_team_id in matchup:
            opp = matchup[1] if matchup[0] == user_team_id else matchup[0]
            series = {'opponent_id': opp, 'user_wins': 0, 'opp_wins': 0, 'round': 'round1'}
            break
    return standings, bracket, series


def generate_playoff_bracket(standings, all_teams):
    """Create playoff bracket from final standings. Top 8 per conference, 1v8 seeding."""
    bracket = {
        'East': {'round1': [], 'round2': [], 'conf_finals': [], 'winner': None},
        'West': {'round1': [], 'round2': [], 'conf_finals': [], 'winner': None},
        'finals': None,
        'champion': None,
        'series': {},
        'current_round': 'round1',
    }
    team_map = {t['id']: t for t in all_teams}

    for conf in ('East', 'West'):
        conf_teams = [tid for tid in standings if CONFERENCE.get(tid) == conf]
        # Sort by win%, tiebreak by total wins
        conf_teams.sort(
            key=lambda t: (
                standings[t]['w'] / max(standings[t]['w'] + standings[t]['l'], 1),
                standings[t]['w'],
            ),
            reverse=True,
        )
        top8 = conf_teams[:8]
        # 1v8, 2v7, 3v6, 4v5
        bracket[conf]['round1'] = [
            (top8[0], top8[7]),
            (top8[1], top8[6]),
            (top8[2], top8[5]),
            (top8[3], top8[4]),
        ]
        for matchup in bracket[conf]['round1']:
            bracket['series'][f"{matchup[0]}v{matchup[1]}"] = {
                'a': matchup[0], 'b': matchup[1],
                'wins_a': 0, 'wins_b': 0, 'winner': None,
            }
    return bracket


# ── LIVE GAME ENGINE ─────────────────────────────────────────────────────────

def _make_player_dict(row):
    """Convert a DataFrame row to a player dict for live game state."""
    return {
        'name': row['PLAYER'],
        'player_id': int(row['PLAYER_ID']),
        'position': row.get('POSITION', '?') or '?',
        'pts': float(row.get('PTS', 0)),
        'reb': float(row.get('REB', 0)),
        'ast': float(row.get('AST', 0)),
        'stl': float(row.get('STL', 0)),
        'blk': float(row.get('BLK', 0)),
        'tov': float(row.get('TOV', 0)),
        'fg_pct': float(row.get('FG_PCT', 0.45)),
        'fg3_pct': float(row.get('FG3_PCT', 0.35)),
        'ft_pct': float(row.get('FT_PCT', 0.75)),
        'fg3a': float(row.get('FG3A', 2)),
        'fga': float(row.get('FGA', 10)),
        'min_avg': float(row.get('MIN', 24)),
        'overall': int(row.get('OVERALL', 70)),
        'stamina': 100,
        'game_pts': 0,
        'game_reb': 0,
        'game_ast': 0,
        'game_stl': 0,
        'game_blk': 0,
        'game_tov': 0,
        'game_fgm': 0,
        'game_fga': 0,
        'game_fg3m': 0,
        'game_fg3a': 0,
        'game_ftm': 0,
        'game_fta': 0,
        'game_plus_minus': 0,
    }


def init_live_game(lineup_df, roster_df, all_stats, all_teams, my_team_id, opponent_id, tactic,
                   difficulty='Easy', rested_players=None, is_home=None):
    """Initialize a live quarter-by-quarter game."""
    hard = difficulty == 'Hard'
    rested_players = rested_players or []
    my_team = next(t for t in all_teams if t['id'] == my_team_id)
    opp_team = next(t for t in all_teams if t['id'] == opponent_id)
    opp_roster = all_stats[all_stats['TEAM_ID'] == opponent_id]

    # User's on-court and bench (rested players are held out entirely)
    starter_names = lineup_df['PLAYER'].tolist()
    injured_names = list(st.session_state.injured_list.keys())
    my_on_court = [_make_player_dict(row) for _, row in lineup_df.iterrows()]
    bench_df = roster_df[
        ~roster_df['PLAYER'].isin(starter_names + injured_names + rested_players)
    ].sort_values('PTS', ascending=False)
    my_bench = [_make_player_dict(row) for _, row in bench_df.iterrows()]

    # Hard mode: apply season stamina carryover to user players
    if hard:
        season_stam = st.session_state.get('season_stamina', {})
        for p in my_on_court + my_bench:
            p['stamina'] = season_stam.get(p['name'], 100)

    # Opponent on-court and bench
    opp_top5 = opp_roster.nlargest(5, 'PTS')
    opp_bench_df = opp_roster[~opp_roster['PLAYER'].isin(opp_top5['PLAYER'])].nlargest(5, 'PTS')
    opp_on_court = [_make_player_dict(row) for _, row in opp_top5.iterrows()]
    opp_bench = [_make_player_dict(row) for _, row in opp_bench_df.iterrows()]

    return {
        'quarter': 1,
        'my_score': 0,
        'opp_score': 0,
        'my_on_court': my_on_court,
        'my_bench': my_bench,
        'opp_on_court': opp_on_court,
        'opp_bench': opp_bench,
        'play_by_play': [],
        'tactic': tactic,
        'quarter_scores': [],
        'injuries': [],
        'subs': [],
        'opponent_id': opponent_id,
        'opponent_name': opp_team['full_name'],
        'my_team_id': my_team_id,
        'my_team_abbr': my_team['abbreviation'],
        'opp_team_abbr': opp_team['abbreviation'],
        'finished': False,
        'difficulty': difficulty,
        'rested': rested_players,
        'is_home': is_home,
        'momentum': momentum_boost(st.session_state.get('results', [])),
    }


def _pop_available_sub(bench):
    """Pop the first bench player who isn't injured-out. Returns None if empty."""
    for i, p in enumerate(bench):
        if not p.get('out'):
            return bench.pop(i)
    return None


def simulate_quarter(live_game):
    """Simulate one quarter. Returns list of play-by-play event strings."""
    q = live_game['quarter']
    is_ot = q > 4
    tactic = live_game['tactic']
    t = TACTICS.get(tactic, TACTICS['Balanced'])
    # Tactics set the pace: more possessions = more points and steadier games;
    # fewer possessions = rock fights where upsets live.
    possessions_per_team = 10 if is_ot else t['live_possessions']
    three_boost = t['three_boost']
    my_abbr = live_game['my_team_abbr']
    opp_abbr = live_game['opp_team_abbr']
    hard = live_game.get('difficulty', 'Easy') == 'Hard'
    events = []
    q_my_pts = 0
    q_opp_pts = 0
    quarter_mins = 5.0 if is_ot else 12.0

    total_possessions = possessions_per_team * 2

    for poss_i in range(total_possessions):
        is_my_team = (poss_i % 2 == 0)
        on_court = live_game['my_on_court'] if is_my_team else live_game['opp_on_court']
        bench = live_game['my_bench'] if is_my_team else live_game['opp_bench']
        team_abbr = my_abbr if is_my_team else opp_abbr
        boost = 1.0

        # Hard mode: opponent gets comeback boost when trailing by 8+
        if hard and not is_my_team:
            deficit = live_game['my_score'] - live_game['opp_score']
            if deficit >= 8:
                boost *= 1.08

        # Home court (±2%) and win-streak momentum (up to +5%) for the user's team
        if is_my_team:
            boost *= home_court_factor(live_game.get('is_home'))
            boost *= live_game.get('momentum', 1.0)

        if not on_court:
            continue

        # Clutch time: Q4/OT within 5 points — stars take over
        margin = abs(live_game['my_score'] - live_game['opp_score'])
        clutch = q >= 4 and margin <= 5

        # Pick player weighted by PTS (stars get the ball even more in clutch time)
        weights = [max(p['pts'], 0.5) ** (1.6 if clutch else 1.0) for p in on_court]
        total_w = sum(weights)
        player = random.choices(on_court, weights=[w / total_w for w in weights])[0]

        # Time remaining
        time_remaining = quarter_mins * (1 - poss_i / total_possessions)
        mins = int(time_remaining)
        secs = int((time_remaining - mins) * 60)
        time_str = f"{mins}:{secs:02d}"
        q_label = f"OT{q - 4}" if is_ot else f"Q{q}"

        # Stamina modifier
        stam_mod = stamina_performance_modifier(player['stamina'])

        # Determine outcome
        fg3_rate = min(player['fg3a'] / max(player['fga'], 1), 0.5) * three_boost
        roll = random.random()

        pts_scored = 0
        event_text = ""

        if roll < 0.40 * stam_mod * boost:
            # Made 2pt
            pts_scored = 2
            player['game_fga'] += 1
            player['game_fgm'] += 1
            teammates = [p for p in on_court if p is not player]
            if teammates and random.random() < 0.6:
                random.choice(teammates)['game_ast'] += 1
            event_text = f"{player['name']} scores inside"
        elif roll < (0.40 + 0.15 * fg3_rate / 0.35) * stam_mod * boost:
            # Made 3pt
            pts_scored = 3
            player['game_fga'] += 1
            player['game_fgm'] += 1
            player['game_fg3a'] += 1
            player['game_fg3m'] += 1
            teammates = [p for p in on_court if p is not player]
            if teammates and random.random() < 0.7:
                random.choice(teammates)['game_ast'] += 1
            event_text = f"{player['name']} hits a 3-pointer"
        elif roll < (0.40 + 0.15 * fg3_rate / 0.35 + 0.10) * stam_mod * boost:
            # Free throw foul
            fts_made = 0
            for _ in range(2):
                player['game_fta'] += 1
                if random.random() < player['ft_pct'] * stam_mod:
                    fts_made += 1
                    player['game_ftm'] += 1
            pts_scored = fts_made
            event_text = f"{player['name']} goes to the line, makes {fts_made}/2 FTs"
        elif roll < 0.90:
            # Miss
            player['game_fga'] += 1
            # Rebound attributed to a random player
            rebounder = random.choice(on_court)
            rebounder['game_reb'] += 1
            # Block credited to a random opponent (~20% of misses)
            opp_court = live_game['opp_on_court'] if is_my_team else live_game['my_on_court']
            if opp_court and random.random() < 0.20:
                random.choice(opp_court)['game_blk'] += 1
            event_text = f"{player['name']} misses"
        else:
            # Turnover
            player['game_tov'] += 1
            opp_court = live_game['opp_on_court'] if is_my_team else live_game['my_on_court']
            if opp_court:
                stealer = random.choice(opp_court)
                stealer['game_stl'] += 1
                event_text = f"Turnover by {player['name']}, stolen by {stealer['name']}"
            else:
                event_text = f"Turnover by {player['name']}"

        if pts_scored > 0:
            player['game_pts'] += pts_scored
            if is_my_team:
                live_game['my_score'] += pts_scored
                q_my_pts += pts_scored
            else:
                live_game['opp_score'] += pts_scored
                q_opp_pts += pts_scored

            # True plus-minus: credit +pts to the scoring team's on-court five
            # and -pts to the defending five (exactly like nba.com). Subs change
            # the on-court lists, so each player only accrues while on the floor.
            scoring_court = live_game['my_on_court'] if is_my_team else live_game['opp_on_court']
            defending_court = live_game['opp_on_court'] if is_my_team else live_game['my_on_court']
            for p in scoring_court:
                p['game_plus_minus'] += pts_scored
            for p in defending_court:
                p['game_plus_minus'] -= pts_scored

        score_str = f"{my_abbr} {live_game['my_score']}, {opp_abbr} {live_game['opp_score']}"
        if clutch and pts_scored > 0:
            event_text = f"🔥 CLUTCH: {event_text}"
        events.append(f"{q_label} {time_str} — {event_text} ({score_str})")

        # Drain stamina
        drain = stamina_drain_per_quarter(player['min_avg'], tactic) / possessions_per_team
        player['stamina'] = max(0, player['stamina'] - drain)
        # Other on-court players drain at 40% rate
        for p in on_court:
            if p is not player:
                p['stamina'] = max(0, p['stamina'] - drain * 0.4)

        # Auto-sub if stamina critically low
        if player['stamina'] < 15:
            sub_in = _pop_available_sub(bench)
            if sub_in:
                on_court.remove(player)
                bench.append(player)
                on_court.append(sub_in)
                sub_event = f"↔ {sub_in['name']} subs in for {player['name']} ({team_abbr})"
                events.append(f"{q_label} {time_str} — {sub_event}")
                live_game['subs'].append(sub_event)

        # Injury check — Hard mode: more frequent and severe
        if hard:
            inj_chance = 0.005 + (100 - player['stamina']) / 2000
        else:
            inj_chance = 0.003 + (100 - player['stamina']) / 3000
        if random.random() < inj_chance and player['name'] not in [i['name'] for i in live_game.get('injuries', [])]:
            severity = random.random()
            if hard:
                if severity < 0.35:
                    duration, tier = random.randint(1, 3), "MINOR"
                elif severity < 0.70:
                    duration, tier = random.randint(3, 8), "MODERATE"
                else:
                    duration, tier = random.randint(8, 20), "SEVERE"
            elif severity < 0.6:
                duration, tier = random.randint(1, 2), "MINOR"
            elif severity < 0.9:
                duration, tier = random.randint(3, 6), "MODERATE"
            else:
                duration, tier = random.randint(8, 15), "SEVERE"
            live_game['injuries'].append({
                'name': player['name'], 'duration': duration, 'tier': tier,
            })
            inj_event = f"🚨 {player['name']} — {tier} injury, OUT {duration} game{'s' if duration > 1 else ''}!"
            events.append(f"{q_label} {time_str} — {inj_event}")
            # Sub out injured player. He may already be on the bench if the
            # low-stamina auto-sub fired earlier this possession — mark him
            # out either way so he can't be subbed back in.
            player['out'] = True
            player['stamina'] = 0
            if player in on_court:
                sub_in = _pop_available_sub(bench)
                if sub_in:
                    on_court.remove(player)
                    bench.append(player)
                    on_court.append(sub_in)

    # Bench recovery
    for p in live_game['my_bench']:
        p['stamina'] = min(100, p['stamina'] + 8)
    for p in live_game['opp_bench']:
        p['stamina'] = min(100, p['stamina'] + 8)

    # Record quarter scores
    live_game['quarter_scores'].append((q_my_pts, q_opp_pts))
    live_game['play_by_play'].extend(events)
    live_game['quarter'] += 1

    # Check if game is over
    if q >= 4 and live_game['my_score'] != live_game['opp_score']:
        live_game['finished'] = True

    return events


def apply_user_subs(live_game, sub_out_name, sub_in_name):
    """Swap one player between on_court and bench."""
    on_court = live_game['my_on_court']
    bench = live_game['my_bench']

    sub_out = next((p for p in on_court if p['name'] == sub_out_name), None)
    sub_in = next((p for p in bench if p['name'] == sub_in_name and not p.get('out')), None)

    if sub_out and sub_in:
        on_court.remove(sub_out)
        bench.remove(sub_in)
        on_court.append(sub_in)
        bench.append(sub_out)
        live_game['subs'].append(f"↔ {sub_in_name} subs in for {sub_out_name}")
        return True
    return False


def finalize_live_game(live_game):
    """Convert live game state into the standard result format."""
    box_score = []

    # Combine on-court and bench for full roster stats
    all_players = live_game['my_on_court'] + live_game['my_bench']
    for p in all_players:
        if p['game_pts'] > 0 or p['game_reb'] > 0 or p['game_ast'] > 0 or p.get('game_fga', 0) > 0:
            box_score.append({
                "Player": p['name'],
                "PLAYER_ID": p['player_id'],
                "PTS": p['game_pts'],
                "REB": p['game_reb'],
                "AST": p['game_ast'],
                "STL": p['game_stl'],
                "BLK": p['game_blk'],
                "TOV": p['game_tov'],
                "PM": p['game_plus_minus'],
                "Stamina Left": int(p['stamina']),
            })

    # Add bench aggregate for remaining contribution
    box_score.append({
        "Player": "Bench / Role Players",
        "PLAYER_ID": 0,
        "PTS": 0, "REB": 0, "AST": 0, "STL": 0, "BLK": 0, "TOV": 0,
        "PM": None, "Stamina Left": 100,
    })

    # Opponent box score
    opp_box_score = []
    all_opp = live_game['opp_on_court'] + live_game['opp_bench']
    for p in all_opp:
        if p['game_pts'] > 0 or p['game_reb'] > 0 or p['game_ast'] > 0 or p.get('game_fga', 0) > 0:
            opp_box_score.append({
                "Player": p['name'],
                "PLAYER_ID": p['player_id'],
                "PTS": p['game_pts'],
                "REB": p['game_reb'],
                "AST": p['game_ast'],
                "STL": p['game_stl'],
                "BLK": p['game_blk'],
                "TOV": p['game_tov'],
                "PM": p['game_plus_minus'],
                "Stamina Left": int(p['stamina']),
            })
    opp_box_score.append({
        "Player": "Bench / Role Players",
        "PLAYER_ID": 0,
        "PTS": 0, "REB": 0, "AST": 0, "STL": 0, "BLK": 0, "TOV": 0,
        "PM": None, "Stamina Left": 100,
    })

    injury_reports = [
        f"🚨 {inj['name']} — {inj['tier']} injury, OUT {inj['duration']} game{'s' if inj['duration'] > 1 else ''}!"
        for inj in live_game.get('injuries', [])
    ]
    sub_reports = live_game.get('subs', [])

    # Register injuries in session state
    for inj in live_game.get('injuries', []):
        st.session_state.injured_list[inj['name']] = inj['duration']

    # Hard mode: record end-of-game stamina for carryover
    if live_game.get('difficulty', 'Easy') == 'Hard':
        new_season_stam = dict(st.session_state.get('season_stamina', {}))
        on_court_names = {p['name'] for p in live_game['my_on_court']}
        for p in all_players:
            if p['name'] in on_court_names:
                new_season_stam[p['name']] = min(100, max(int(p['stamina']) + 15, 70))
            else:
                new_season_stam[p['name']] = min(100, new_season_stam.get(p['name'], 100) + 25)
        # Load management: rested players sit the whole game and recover fully.
        for name in live_game.get('rested', []):
            new_season_stam[name] = 100
        st.session_state.season_stamina = new_season_stam

    return (
        live_game['my_score'],
        live_game['opp_score'],
        box_score,
        injury_reports,
        sub_reports,
        live_game['opponent_name'],
        opp_box_score,
    )
