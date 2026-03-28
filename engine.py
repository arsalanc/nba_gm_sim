import streamlit as st
import random
from utils import compute_team_strength, get_win_probability, CONFERENCE


def simulate_game(lineup_df, roster_df, tactic, all_stats, all_teams, my_team_id, rested_players,
                  opponent_team_id=None):
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
    opp_bench = opp_roster[~opp_roster['PLAYER'].isin(opp_top5['PLAYER'])].nlargest(5, 'PTS')

    opp_score = 0
    for _, opp_player in opp_top5.iterrows():
        # Opponent players have randomised per-game stamina (fatigue varies across a season)
        opp_stam = random.randint(55, 100)
        opp_pts = int(opp_player['PTS'] * random.uniform(0.8, 1.2) * (opp_stam / 100))

        # Opponent injury / foul-out — sub in bench player
        opp_inj_chance = 0.03 + ((100 - opp_stam) / 500)
        if random.random() < opp_inj_chance and not opp_bench.empty:
            opp_pts = int(opp_pts * 0.2)
            sub_row = opp_bench.iloc[0]
            sub_stam = random.randint(70, 100)
            opp_pts += int(sub_row['PTS'] * random.uniform(0.7, 1.0) * (sub_stam / 100) * 0.7)
            injury_reports.append(
                f"🚨 {opp_player['PLAYER']} ({opp_team_name}) left the game!"
            )
            opp_bench = opp_bench.iloc[1:]  # remove used sub

        opp_score += opp_pts

    # Bench / role-player contribution (rest of the rotation)
    opp_bench_contribution = random.randint(30, 45)
    opp_score += opp_bench_contribution

    starter_names = lineup_df['PLAYER'].tolist()
    injured_names = list(st.session_state.injured_list.keys())
    drain = 20 if tactic == "Grit & Grind" else 15

    # Build bench pool sorted by PTS
    bench_df = roster_df[
        ~roster_df['PLAYER'].isin(starter_names + injured_names + rested_players)
    ].sort_values('PTS', ascending=False)
    bench_pool = bench_df.to_dict('records')

    for _, player in lineup_df.iterrows():
        name = player['PLAYER']
        pid = int(player['PLAYER_ID'])
        current_stam = st.session_state.stamina.get(name, 100)

        # Sub out if stamina critically low
        if current_stam < 30 and bench_pool:
            sub = bench_pool.pop(0)
            sub_name = sub['PLAYER']
            sub_stam = st.session_state.stamina.get(sub_name, 100)
            sub_pts = int(sub['PTS'] * random.uniform(0.7, 1.1) * (sub_stam / 100) * 0.7)
            new_sub_stam = max(0, sub_stam - 10)
            st.session_state.stamina[sub_name] = new_sub_stam
            total_score += sub_pts
            box_score.append({
                "Player": f"↔ {sub_name} (sub for {name.split()[-1]})",
                "PLAYER_ID": int(sub['PLAYER_ID']),
                "Points": sub_pts,
                "Stamina Left": new_sub_stam,
            })
            sub_reports.append(f"↔ {sub_name} subbed in for {name}")
            # Starter sits — no further drain
            box_score.append({
                "Player": name,
                "PLAYER_ID": pid,
                "Points": 0,
                "Stamina Left": current_stam,
            })
            continue

        fatigue_multiplier = current_stam / 100
        pts = int(player['PTS'] * random.uniform(0.8, 1.2) * fatigue_multiplier)

        # Tiered injury check
        injury_chance = 0.03 + ((100 - current_stam) / 500)
        if random.random() < injury_chance and name not in st.session_state.injured_list:
            pts = int(pts * 0.2)
            severity = random.random()
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
        st.session_state.stamina[name] = new_stam
        total_score += pts
        box_score.append({
            "Player": name,
            "PLAYER_ID": pid,
            "Points": pts,
            "Stamina Left": new_stam,
        })

    # Bench / role-player contribution (rest of the rotation)
    bench_contribution = random.randint(30, 45)
    total_score += bench_contribution
    box_score.append({
        "Player": "Bench / Role Players",
        "PLAYER_ID": 0,
        "Points": bench_contribution,
        "Stamina Left": 100,
    })

    return total_score, opp_score, box_score, injury_reports, sub_reports, opp_team_name


def post_game_updates(starter_names, rested_players, roster_df):
    """Tick down injury counters and recover bench / rested player stamina."""
    # Decrement first, then remove fully-recovered players
    for p in list(st.session_state.injured_list.keys()):
        st.session_state.injured_list[p] -= 1
    healed = [p for p, g in st.session_state.injured_list.items() if g <= 0]
    for p in healed:
        del st.session_state.injured_list[p]

    # Stamina recovery for non-starters
    for _, player in roster_df.iterrows():
        name = player['PLAYER']
        if name in starter_names or name in st.session_state.injured_list:
            continue
        recovery = 40 if name in rested_players else 20
        current = st.session_state.stamina.get(name, 100)
        st.session_state.stamina[name] = min(100, current + recovery)


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


def auto_select_lineup(roster_df, injured_list, stamina):
    """Pick best 5 healthy players by effective scoring for batch sim."""
    injured_names = list(injured_list.keys())
    healthy = roster_df[~roster_df['PLAYER'].isin(injured_names)].copy()
    healthy['_eff'] = healthy['PTS'] * healthy['PLAYER'].map(
        lambda n: stamina.get(n, 100) / 100
    )
    top5 = healthy.nlargest(5, '_eff')
    return top5.drop(columns=['_eff']), []


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
