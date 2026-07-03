import streamlit as st

from utils import team_logo_url, save_state
from offseason import ai_draft_pick, prospect_stat_row


def _prospect_line(p):
    return (f"**{p['name']}** — `{p['position']}` {p['archetype']}, {p['age']}y · "
            f"OVR **{p['ovr']}** · Potential **{p['grade']}** "
            f"(projects {p['scout_low']}–{p['scout_high']})")


def _finalize_draft(ds, all_teams):
    """Turn picks into league rookies and roll over to the next season."""
    sn = st.session_state.season_number
    rows = list(st.session_state.rookie_rows)
    for pk in ds['picks']:
        rows.append(prospect_stat_row(pk['prospect'], pk['team_id'], sn))
    st.session_state.rookie_rows = rows
    st.session_state.season_number = sn + 1

    st.session_state.results = []
    st.session_state.season_pts = {}
    st.session_state.injured_list = {}
    st.session_state.standings = {t['id']: {'w': 0, 'l': 0} for t in all_teams}
    st.session_state.games_played = 0
    st.session_state.season_phase = 'regular'
    st.session_state.playoff_bracket = None
    st.session_state.current_series = None
    st.session_state.last_game_result = None
    st.session_state.batch_results = None
    st.session_state.season_stamina = {}
    st.session_state.trade_cooldown = 0
    st.session_state.draft_state = None
    st.session_state.offseason_report = None
    save_state()
    st.rerun()


def render(my_team, current_team_id, all_teams):
    ds = st.session_state.draft_state
    report = st.session_state.offseason_report or {}
    team_map = {t['id']: t for t in all_teams}
    sn = st.session_state.season_number

    st.title(f"🏛️ Offseason — Season {sn} Draft")

    order = ds['order']
    total = len(order)
    cur_i = len(ds['picks'])
    user_pick_no = order.index(current_team_id) + 1

    # ── Offseason report ─────────────────────────────────────────────────
    with st.expander("📜 Offseason Report — aging & retirements", expanded=(cur_i == 0)):
        retired = report.get('retired', [])
        risers = report.get('risers', [])
        fallers = report.get('fallers', [])
        rep_ret, rep_up, rep_down = st.columns(3)
        with rep_ret:
            st.markdown("**👋 Retirements**")
            if retired:
                for r in retired[:10]:
                    st.caption(f"{r['name']} — age {r['age']}, OVR {r['ovr']}")
                if len(retired) > 10:
                    st.caption(f"…and {len(retired) - 10} more")
            else:
                st.caption("No retirements this year.")
        with rep_up:
            st.markdown("**📈 On the rise**")
            for r in risers[:8]:
                st.caption(f"{r['name']} ({r['age']}y) → OVR {r['ovr']} (+{r['delta']})")
        with rep_down:
            st.markdown("**📉 Declining**")
            for r in fallers[:8]:
                st.caption(f"{r['name']} ({r['age']}y) → OVR {r['ovr']} ({r['delta']})")

    st.divider()

    taken = {pk['prospect']['name'] for pk in ds['picks']}
    remaining = [p for p in ds['prospects'] if p['name'] not in taken]

    # ── Draft flow ────────────────────────────────────────────────────────
    if cur_i >= total:
        st.success("🏁 The draft is complete!")
        my_picks = [(i + 1, pk) for i, pk in enumerate(ds['picks'])
                    if pk['team_id'] == current_team_id]
        for pick_no, pk in my_picks:
            st.markdown(f"🎓 Your pick **#{pick_no}**: {_prospect_line(pk['prospect'])}")
        if st.button(f"🚀 Start Season {sn + 1}", type="primary"):
            _finalize_draft(ds, all_teams)

    elif order[cur_i] == current_team_id:
        st.subheader(f"🎓 You're on the clock — pick #{cur_i + 1}")
        st.caption("Scouts see current ability (OVR) and a **potential grade with a projected "
                   "range** — the true ceiling is hidden. Lottery talents can bust; "
                   "late-round picks can become stars.")
        board = remaining[:15]
        choice = st.selectbox(
            "Draft board (scout rank order):",
            range(len(board)),
            format_func=lambda i: (f"{board[i]['name']} — {board[i]['position']} · "
                                   f"{board[i]['archetype']} · {board[i]['age']}y · "
                                   f"OVR {board[i]['ovr']} · {board[i]['grade']} "
                                   f"({board[i]['scout_low']}–{board[i]['scout_high']})"),
            key=f"draft_choice_{cur_i}",
        )
        st.markdown(_prospect_line(board[choice]))
        if st.button(f"✅ Draft {board[choice]['name']}", type="primary"):
            ds['picks'].append({'team_id': current_team_id, 'prospect': board[choice]})
            save_state()
            st.rerun()

    else:
        on_clock = team_map[order[cur_i]]
        st.info(f"🎟️ You hold pick **#{user_pick_no}**. On the clock: "
                f"pick #{cur_i + 1} — **{on_clock['full_name']}**")
        past_user = cur_i > order.index(current_team_id)
        label = "⏩ Sim remaining picks" if past_user else f"⏩ Sim to your pick (#{user_pick_no})"
        if st.button(label, type="primary"):
            while len(ds['picks']) < total and order[len(ds['picks'])] != current_team_id:
                taken = {pk['prospect']['name'] for pk in ds['picks']}
                rem = [p for p in ds['prospects'] if p['name'] not in taken]
                ds['picks'].append({
                    'team_id': order[len(ds['picks'])],
                    'prospect': ai_draft_pick(rem),
                })
            save_state()
            st.rerun()

    # ── Board so far ─────────────────────────────────────────────────────
    if ds['picks']:
        st.divider()
        with st.expander(f"📋 Draft board ({len(ds['picks'])}/{total} picks)", expanded=True):
            for i, pk in enumerate(ds['picks']):
                p = pk['prospect']
                is_user = pk['team_id'] == current_team_id
                rc = st.columns([0.5, 0.6, 5])
                rc[0].write(f"**#{i + 1}**")
                rc[1].image(team_logo_url(pk['team_id']), width=28)
                line = (f"{'👉 ' if is_user else ''}**{p['name']}** — {p['position']} · "
                        f"{p['archetype']} · OVR {p['ovr']} · {p['grade']}")
                rc[2].markdown(line)
