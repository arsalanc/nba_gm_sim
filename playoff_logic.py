import streamlit as st

from engine import simulate_playoff_series
from utils import CONFERENCE


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
