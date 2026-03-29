import streamlit as st

from utils import CONFERENCE, team_logo_url

_BRACKET_CSS = """
<style>
.bracket-container {
    display: flex;
    align-items: center;
    gap: 24px;
    overflow-x: auto;
    padding: 16px 0;
}
.bracket-round {
    display: flex;
    flex-direction: column;
    gap: 24px;
    justify-content: center;
    min-width: 180px;
}
.bracket-round-r2 { gap: 72px; }
.bracket-round-cf { gap: 168px; }
.bracket-round-label {
    text-align: center;
    font-weight: bold;
    font-size: 0.85rem;
    color: #888;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.bracket-matchup {
    border: 1px solid #444;
    border-radius: 6px;
    overflow: hidden;
    background: #1a1a2e;
}
.bracket-team {
    display: flex;
    align-items: center;
    padding: 6px 10px;
    gap: 8px;
    font-size: 0.9rem;
    border-bottom: 1px solid #333;
    min-height: 38px;
}
.bracket-team:last-child { border-bottom: none; }
.bracket-tbd {
    color: #555;
    font-style: italic;
    justify-content: center;
}
.bracket-winner {
    background: #1b3a2a;
    font-weight: bold;
}
.bracket-loser {
    opacity: 0.45;
}
.bracket-user .bracket-name {
    color: #4da6ff;
    font-weight: bold;
}
.bracket-logo {
    width: 24px;
    height: 24px;
    object-fit: contain;
}
.bracket-seed {
    color: #888;
    font-size: 0.75rem;
    min-width: 14px;
}
.bracket-name {
    font-weight: 600;
    min-width: 36px;
}
.bracket-record {
    color: #999;
    font-size: 0.8rem;
    margin-left: auto;
}
.bracket-wins {
    background: #333;
    color: #fff;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 0.8rem;
    font-weight: bold;
    min-width: 18px;
    text-align: center;
}
.bracket-winner .bracket-wins {
    background: #2d7a4a;
}
.bracket-champion {
    text-align: center;
    padding: 16px;
    border: 2px solid #ffd700;
    border-radius: 8px;
    background: linear-gradient(135deg, #1a1a2e 0%, #2a1a0e 100%);
}
.bracket-champion img {
    width: 64px;
    height: 64px;
    object-fit: contain;
}
.bracket-finals-label {
    text-align: center;
    font-size: 1.1rem;
    font-weight: bold;
    color: #ffd700;
    margin-bottom: 12px;
}
</style>
"""


def _bracket_cell(tid, team_map_by_id, standings, current_team_id,
                  series_data=None, seed=None, is_winner=False, is_loser=False):
    """Generate HTML for one team cell in the bracket."""
    if tid is None:
        return '<div class="bracket-team bracket-tbd">TBD</div>'
    info = team_map_by_id.get(tid, {})
    abbr = info.get('abbreviation', '?')
    logo = team_logo_url(tid)
    rec = standings.get(tid, {'w': 0, 'l': 0})
    record = f"{rec['w']} - {rec['l']}"
    wins = ''
    if series_data:
        w = series_data['wins_a'] if series_data['a'] == tid else series_data['wins_b']
        wins = f'<span class="bracket-wins">{w}</span>'
    seed_str = f'<span class="bracket-seed">{seed}</span>' if seed else ''
    cls = 'bracket-team'
    if is_winner:
        cls += ' bracket-winner'
    if is_loser:
        cls += ' bracket-loser'
    if tid == current_team_id:
        cls += ' bracket-user'
    return (
        f'<div class="{cls}">'
        f'  <img src="{logo}" class="bracket-logo">'
        f'  {seed_str}'
        f'  <span class="bracket-name">{abbr}</span>'
        f'  <span class="bracket-record">{record}</span>'
        f'  {wins}'
        f'</div>'
    )


def _matchup_html(a_id, b_id, bracket, team_map_by_id, standings, current_team_id,
                  seed_a=None, seed_b=None):
    """Generate HTML for a single matchup box."""
    key = f"{a_id}v{b_id}"
    s = bracket['series'].get(key, {})
    winner = s.get('winner')
    a_winner = winner == a_id if winner else False
    b_winner = winner == b_id if winner else False
    a_loser = winner is not None and not a_winner
    b_loser = winner is not None and not b_winner
    return (
        f'<div class="bracket-matchup">'
        f'  {_bracket_cell(a_id, team_map_by_id, standings, current_team_id, s, seed_a, a_winner, a_loser)}'
        f'  {_bracket_cell(b_id, team_map_by_id, standings, current_team_id, s, seed_b, b_winner, b_loser)}'
        f'</div>'
    )


def _tbd_matchup():
    return (
        '<div class="bracket-matchup">'
        '  <div class="bracket-team bracket-tbd">TBD</div>'
        '  <div class="bracket-team bracket-tbd">TBD</div>'
        '</div>'
    )


def render(current_team_id, all_teams):
    bracket = st.session_state.playoff_bracket
    standings = st.session_state.standings

    if not bracket:
        season_length = st.session_state.get('season_length', 82)
        st.info(f"The playoff bracket will appear here once the regular season is complete ({season_length} games).")
        return

    team_map_by_id = {t['id']: t for t in all_teams}

    # Compute seeds per conference
    conf_seeds = {}
    for conf in ('East', 'West'):
        conf_teams = [tid for tid in standings if CONFERENCE.get(tid) == conf]
        conf_teams.sort(
            key=lambda t: (
                standings[t]['w'] / max(standings[t]['w'] + standings[t]['l'], 1),
                standings[t]['w'],
            ),
            reverse=True,
        )
        for i, tid in enumerate(conf_teams[:8], 1):
            conf_seeds[tid] = i

    st.markdown(_BRACKET_CSS, unsafe_allow_html=True)

    def _build_conf_rounds(conf):
        conf_data = bracket[conf]

        r1 = conf_data.get('round1', [])
        r1_html = ''
        for a_id, b_id in r1:
            r1_html += _matchup_html(a_id, b_id, bracket, team_map_by_id, standings, current_team_id,
                                     conf_seeds.get(a_id), conf_seeds.get(b_id))

        r2 = conf_data.get('round2', [])
        r2_html = ''
        if r2:
            for a_id, b_id in r2:
                r2_html += _matchup_html(a_id, b_id, bracket, team_map_by_id, standings, current_team_id,
                                         conf_seeds.get(a_id), conf_seeds.get(b_id))
        else:
            r2_html = _tbd_matchup() + _tbd_matchup()

        cf = conf_data.get('conf_finals', [])
        cf_html = ''
        if cf:
            for a_id, b_id in cf:
                cf_html += _matchup_html(a_id, b_id, bracket, team_map_by_id, standings, current_team_id,
                                         conf_seeds.get(a_id), conf_seeds.get(b_id))
        else:
            cf_html = _tbd_matchup()

        return r1_html, r2_html, cf_html

    west_r1, west_r2, west_cf = _build_conf_rounds('West')
    east_r1, east_r2, east_cf = _build_conf_rounds('East')

    # Finals center column
    if bracket.get('finals'):
        a_id, b_id = bracket['finals']
        finals_html = _matchup_html(a_id, b_id, bracket, team_map_by_id, standings, current_team_id)
    else:
        finals_html = _tbd_matchup()

    champion_html = ''
    if bracket.get('champion'):
        champ = team_map_by_id.get(bracket['champion'], {})
        champion_html = (
            f'<div class="bracket-champion" style="margin-top:12px;">'
            f'  <img src="{team_logo_url(bracket["champion"])}">'
            f'  <div style="font-size:1.1rem;font-weight:bold;color:#ffd700;margin-top:6px;">'
            f'    🏆 {champ.get("full_name", "?")} 🏆'
            f'  </div>'
            f'  <div style="color:#ccc;font-size:0.85rem;">NBA Champions</div>'
            f'</div>'
        )

    # Full bracket: West (L→R) | Finals | East (R→L mirrored)
    html = (
        f'<div style="overflow-x:auto;padding:12px 0;">'
        f'<div style="display:flex;align-items:center;gap:16px;min-width:max-content;">'

        # West: R1 → R2 → CF (left to right)
        f'  <div class="bracket-round" style="align-items:flex-start;">'
        f'    <div class="bracket-round-label">West · First Round</div>'
        f'    {west_r1}'
        f'  </div>'
        f'  <div class="bracket-round bracket-round-r2" style="align-items:flex-start;">'
        f'    <div class="bracket-round-label">Semifinals</div>'
        f'    {west_r2}'
        f'  </div>'
        f'  <div class="bracket-round bracket-round-cf" style="align-items:flex-start;">'
        f'    <div class="bracket-round-label">Conf Finals</div>'
        f'    {west_cf}'
        f'  </div>'

        # Finals center
        f'  <div style="display:flex;flex-direction:column;align-items:center;gap:8px;min-width:180px;">'
        f'    <div class="bracket-finals-label" style="margin-bottom:4px;">NBA Finals</div>'
        f'    {finals_html}'
        f'    {champion_html}'
        f'  </div>'

        # East: CF → R2 → R1 (right to left mirror — rendered reversed)
        f'  <div class="bracket-round bracket-round-cf" style="align-items:flex-end;">'
        f'    <div class="bracket-round-label">Conf Finals</div>'
        f'    {east_cf}'
        f'  </div>'
        f'  <div class="bracket-round bracket-round-r2" style="align-items:flex-end;">'
        f'    <div class="bracket-round-label">Semifinals</div>'
        f'    {east_r2}'
        f'  </div>'
        f'  <div class="bracket-round" style="align-items:flex-end;">'
        f'    <div class="bracket-round-label">East · First Round</div>'
        f'    {east_r1}'
        f'  </div>'

        f'</div>'
        f'</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
