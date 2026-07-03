"""Franchise Mode offseason: draft prospects, lottery, aging, retirement.

Prospects are procedurally generated (archetype + quality roll + hidden
potential) because real incoming rookies have no NBA stats for the engine to
use, and future draft classes don't exist in any API. League evolution is
stored as compact session-state deltas (progression multipliers, retired
names, rookie rows) and re-applied to the freshly loaded league data each
rerun — the same pattern as trade overrides.
"""
import random

import pandas as pd

from utils import estimate_salary

ROOKIE_ID_BASE = 90_000_000

FIRST_NAMES = [
    "Jalen", "Marcus", "Tyrese", "Darius", "Malik", "DeAndre", "Trey", "Cade",
    "Jaden", "Amari", "Isaiah", "Jordan", "Devin", "Anthony", "Cameron", "Josh",
    "Aaron", "Keyonte", "Bryce", "Kris", "Terrence", "Xavier", "Elijah", "Noah",
    "Caleb", "Micah", "Andre", "Victor", "Luka", "Nikola", "Dario", "Bogdan",
    "Franz", "Moritz", "Killian", "Rui", "Shai", "Lonnie", "Dejounte", "Desmond",
    "Keegan", "Jabari", "Paolo", "Ausar", "Amen", "Brandon", "Gradey", "Dalton",
]
LAST_NAMES = [
    "Washington", "Carter", "Brooks", "Johnson", "Williams", "Mitchell", "Henderson",
    "Thompson", "Robinson", "Jackson", "Harris", "Lewis", "Walker", "Young", "Allen",
    "King", "Wright", "Scott", "Green", "Baker", "Adams", "Nelson", "Hill", "Rivers",
    "Coleman", "Bryant", "Foster", "Murphy", "Bell", "Ward", "Cook", "Bailey",
    "Reed", "Kelly", "Howard", "Gray", "Watson", "Price", "Sanders", "Barnes",
    "Ross", "Henry", "Long", "Powell", "Butler", "Simmons", "Patterson", "Hughes",
    "Vukovic", "Petrovic", "Markovic", "Okafor", "Diallo", "Sarr", "Traore", "Petit",
]

# Stat-line shapes at a given production level. 'pos' feeds the POSITION column.
ARCHETYPES = {
    'Scoring Guard':    dict(pos='G', pts=1.35, reb=0.55, ast=0.90, stl=0.9, blk=0.2,
                             fg3a=6.0, fga=16.0, fg_pct=.44, fg3_pct=.36, ft_pct=.83),
    'Playmaker':        dict(pos='G', pts=0.95, reb=0.60, ast=1.80, stl=1.1, blk=0.2,
                             fg3a=4.0, fga=12.0, fg_pct=.45, fg3_pct=.35, ft_pct=.80),
    '3&D Wing':         dict(pos='F', pts=1.00, reb=0.90, ast=0.60, stl=1.3, blk=0.6,
                             fg3a=6.0, fga=11.0, fg_pct=.45, fg3_pct=.38, ft_pct=.78),
    'Two-Way Forward':  dict(pos='F', pts=1.15, reb=1.20, ast=0.80, stl=1.0, blk=0.8,
                             fg3a=4.0, fga=13.0, fg_pct=.47, fg3_pct=.34, ft_pct=.76),
    'Rim-Running Big':  dict(pos='C', pts=1.00, reb=1.90, ast=0.40, stl=0.6, blk=1.7,
                             fg3a=0.5, fga=9.0, fg_pct=.62, fg3_pct=.25, ft_pct=.65),
    'Stretch Big':      dict(pos='C', pts=1.05, reb=1.50, ast=0.50, stl=0.5, blk=1.2,
                             fg3a=5.0, fga=12.0, fg_pct=.48, fg3_pct=.37, ft_pct=.75),
}

_GRADES = [(88, 'A+'), (84, 'A'), (80, 'B+'), (76, 'B'), (72, 'C+'), (0, 'C')]


def _grade(potential):
    for cut, g in _GRADES:
        if potential >= cut:
            return g


def generate_draft_class(existing_names, season_number, n=45, rng=None):
    """Generate n prospects, best scout rank first. 'potential' is the hidden
    true ceiling; scouts only ever see grade + [scout_low, scout_high]."""
    rng = rng or random.Random()
    used = set(existing_names)
    prospects = []
    for i in range(n):
        while True:
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            if name not in used:
                used.add(name)
                break
        arch_name = rng.choice(list(ARCHETYPES))
        cur = max(60, min(84, int(82 - i * 0.45 + rng.uniform(-2, 2))))
        age = rng.choice([19, 19, 20, 20, 21, 22])
        # Younger prospects carry more upside — and more bust risk (gauss can go ~0)
        upside = max(0, int(rng.gauss(9 - (age - 19) * 1.5, 4)))
        potential = min(99, cur + upside)
        wiggle = rng.randint(2, 4)
        prospects.append({
            'name': name, 'archetype': arch_name, 'position': ARCHETYPES[arch_name]['pos'],
            'age': age, 'ovr': cur, 'potential': potential,
            'grade': _grade(potential),
            'scout_low': max(cur, potential - wiggle),
            'scout_high': min(99, potential + wiggle),
            'player_id': ROOKIE_ID_BASE + season_number * 1000 + i,
        })
    return prospects


def prospect_stat_row(p, team_id, draft_season):
    """Convert a drafted prospect into an all_stats-compatible row."""
    arch = ARCHETYPES[p['archetype']]
    prod = (p['ovr'] - 54) * 0.55           # scoring production scale
    pts = round(prod * arch['pts'], 1)
    return {
        'PLAYER': p['name'], 'PLAYER_ID': p['player_id'], 'TEAM_ID': int(team_id),
        'PTS': pts,
        'REB': round((p['ovr'] - 54) * 0.30 * arch['reb'], 1),
        'AST': round((p['ovr'] - 54) * 0.20 * arch['ast'], 1),
        'STL': round(arch['stl'] * (0.4 + (p['ovr'] - 54) / 25.0), 1),
        'BLK': round(arch['blk'] * (0.4 + (p['ovr'] - 54) / 25.0), 1),
        'TOV': round(pts * 0.15, 1),
        'FGA': round(arch['fga'] * prod / 12.0, 1),
        'FG3A': round(arch['fg3a'] * prod / 12.0, 1),
        'FG_PCT': arch['fg_pct'], 'FG3_PCT': arch['fg3_pct'], 'FT_PCT': arch['ft_pct'],
        'MIN': round(min(34.0, 10 + prod * 1.6), 1),
        'OVERALL': int(p['ovr']),
        'SALARY': estimate_salary(pts),
        'POSITION': p['position'],
        'AGE': int(p['age']),
        '_POTENTIAL': int(p['potential']),
        '_DRAFT_SEASON': int(draft_season),
    }


def compute_draft_order(standings, rng=None):
    """Reverse-standings order with a simplified NBA lottery: the 14 worst
    teams enter weighted draws for the top 4 picks."""
    rng = rng or random.Random()
    ids = sorted(
        standings,
        key=lambda t: (
            standings[t]['w'] / max(standings[t]['w'] + standings[t]['l'], 1),
            standings[t]['w'],
        ),
    )  # worst record first
    lottery = ids[:14]
    weights = [140, 140, 140, 125, 105, 90, 75, 60, 45, 30, 20, 15, 10, 5]
    pool, w, top4 = lottery[:], weights[:], []
    for _ in range(4):
        pick = rng.choices(pool, weights=w)[0]
        i = pool.index(pick)
        pool.pop(i)
        w.pop(i)
        top4.append(pick)
    return top4 + [t for t in lottery if t not in top4] + ids[14:]


def ai_draft_pick(remaining, rng=None):
    """AI teams draft near-best-available with a little randomness so drafts
    don't play out identically."""
    rng = rng or random.Random()
    pool = sorted(remaining,
                  key=lambda p: p['ovr'] + (p['scout_low'] + p['scout_high']) / 2,
                  reverse=True)[:6]
    weights = [8, 5, 3, 2, 1, 1][:len(pool)]
    return rng.choices(pool, weights=weights)[0]


def compute_offseason_aging(df, progression, rng=None):
    """One offseason of aging for every player in the (already-evolved) league.

    Returns (new_progression, retired, risers, fallers). Progression is
    cumulative against the base loaded data: 'ovr' is a flat OVERALL delta,
    'mult' scales counting stats.
    """
    rng = rng or random.Random()
    new_prog = {k: dict(v) for k, v in progression.items()}
    retired, risers, fallers = [], [], []

    for _, row in df.iterrows():
        name = row['PLAYER']
        ovr = int(row['OVERALL'])
        age = int(row['AGE']) if 'AGE' in row and pd.notna(row['AGE']) else 27
        pot = row.get('_POTENTIAL')

        if pot is not None and pd.notna(pot) and ovr < int(pot) and age <= 25:
            # Young draftee developing toward his hidden ceiling
            delta = min(int(pot) - ovr, rng.randint(2, 6))
        elif age <= 22:
            delta = rng.randint(1, 3)
        elif age <= 26:
            delta = rng.randint(0, 2)
        elif age <= 29:
            delta = rng.randint(-1, 1)
        elif age <= 32:
            delta = rng.randint(-3, -1)
        else:
            delta = rng.randint(-5, -2)

        new_ovr = max(40, min(99, ovr + delta))

        retire_chance = 0.0
        if age >= 38:
            retire_chance = 0.9
        elif age >= 35:
            retire_chance = 0.25 + (0.35 if new_ovr < 72 else 0.0)
        elif age >= 33 and new_ovr < 65:
            retire_chance = 0.4
        if rng.random() < retire_chance:
            retired.append({'name': name, 'age': age, 'ovr': ovr})
            continue

        p = new_prog.setdefault(name, {'ovr': 0, 'mult': 1.0})
        p['ovr'] += delta
        p['mult'] = max(0.35, min(2.0, p['mult'] * (1 + delta * 0.025)))

        if delta >= 4:
            risers.append({'name': name, 'age': age, 'delta': delta, 'ovr': new_ovr})
        elif delta <= -4:
            fallers.append({'name': name, 'age': age, 'delta': delta, 'ovr': new_ovr})

    risers.sort(key=lambda r: -r['delta'])
    fallers.sort(key=lambda r: r['delta'])
    return new_prog, retired, risers, fallers


def apply_league_evolution(all_stats, progression, retired_names, rookie_rows, season_number):
    """Re-apply all franchise-mode deltas to freshly loaded league data:
    drop retirees, add draftees, apply aging, refresh salaries and ages."""
    if not (progression or retired_names or rookie_rows):
        return all_stats
    df = all_stats.copy()
    if retired_names:
        df = df[~df['PLAYER'].isin(retired_names)]
    if rookie_rows:
        rk = pd.DataFrame(rookie_rows)
        rk = rk[~rk['PLAYER'].isin(df['PLAYER'])]
        df = pd.concat([df, rk], ignore_index=True)
    if progression:
        ovr_map = {n: p['ovr'] for n, p in progression.items()}
        mult_map = {n: p['mult'] for n, p in progression.items()}
        df['OVERALL'] = (df['OVERALL'] + df['PLAYER'].map(ovr_map).fillna(0)).clip(40, 99).astype(int)
        m = df['PLAYER'].map(mult_map).fillna(1.0)
        for c in ('PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV'):
            if c in df.columns:
                df[c] = (df[c] * m).round(1)
        df['SALARY'] = df['PTS'].apply(estimate_salary)
    # Effective age this season: veterans age from season 1; draftees age from
    # the season after they were drafted.
    if 'AGE' in df.columns:
        if '_DRAFT_SEASON' in df.columns:
            drafted = df['_DRAFT_SEASON'].fillna(0)
            elapsed = (season_number - 1) - drafted.where(drafted > 0, 0)
        else:
            elapsed = season_number - 1
        df['AGE'] = (df['AGE'].fillna(27) + elapsed).clip(18, 45).astype(int)
    return df
