import streamlit as st

from utils import team_logo_url, fmt_salary, evaluate_trade, save_state


def render(my_team, current_team_id, roster, all_teams, all_stats, acquired, difficulty, hard):
    st.subheader("Trade Desk")
    st.caption(
        "Real NBA salary matching rules apply: incoming salary must be ≤ outgoing × 1.25 + $100K. "
        "The AI GM will reject lopsided deals."
    )

    other_teams_list = [t for t in all_teams if t['id'] != current_team_id]
    team_name_map = {t['full_name']: t for t in other_teams_list}
    partner_name = st.selectbox("Trade Partner:", sorted(team_name_map.keys()), key="trade_partner")
    partner_team = team_name_map[partner_name]
    ptl_col, _ = st.columns([1, 5])
    ptl_col.image(team_logo_url(partner_team['id']), width=80)

    # Build partner roster, excluding players already acquired by user
    partner_roster = all_stats[all_stats['TEAM_ID'] == partner_team['id']].copy()
    partner_roster = partner_roster[~partner_roster['PLAYER'].isin(acquired)]

    col_mine, col_theirs = st.columns(2)

    with col_mine:
        lc, nc = st.columns([1, 5])
        lc.image(team_logo_url(current_team_id), width=40)
        nc.write(f"**Your players** ({my_team['abbreviation']})")
        my_labels = roster.apply(
            lambda r: f"[{r.get('POSITION') or '?'}] {r['PLAYER']} — {r['PTS']:.1f} PPG, OVR {r['OVERALL']}, {fmt_salary(r['SALARY'])}", axis=1
        ).tolist()
        my_name_map = dict(zip(my_labels, roster['PLAYER'].tolist()))
        my_selections = st.multiselect(
            "Send (1–3 players):", options=my_labels, key="my_trade_players"
        )

    with col_theirs:
        lc, nc = st.columns([1, 5])
        lc.image(team_logo_url(partner_team['id']), width=40)
        nc.write(f"**{partner_name} players**")
        their_labels = partner_roster.apply(
            lambda r: f"[{r.get('POSITION') or '?'}] {r['PLAYER']} — {r['PTS']:.1f} PPG, OVR {r['OVERALL']}, {fmt_salary(r['SALARY'])}", axis=1
        ).tolist()
        their_name_map = dict(zip(their_labels, partner_roster['PLAYER'].tolist()))
        their_selections = st.multiselect(
            "Receive (1–3 players):", options=their_labels, key="their_trade_players"
        )

    if my_selections and their_selections:
        if len(my_selections) > 3 or len(their_selections) > 3:
            st.error("Maximum 3 players per side.")
        else:
            my_names = [my_name_map[l] for l in my_selections]
            their_names = [their_name_map[l] for l in their_selections]
            my_trade_df = roster[roster['PLAYER'].isin(my_names)]
            their_trade_df = partner_roster[partner_roster['PLAYER'].isin(their_names)]

            accepted, my_pts, their_pts, my_sal, their_sal = evaluate_trade(my_trade_df, their_trade_df, difficulty)

            salary_limit = my_sal * 1.25 + 100_000
            st.write(
                f"**Trade summary:** You send {fmt_salary(my_sal)} / {my_pts:.1f} PPG "
                f"→ Receive {fmt_salary(their_sal)} / {their_pts:.1f} PPG"
            )
            if their_sal > salary_limit:
                st.error(f"Salary mismatch: max you can receive is {fmt_salary(salary_limit)}")
            elif not accepted:
                st.error(
                    f"{partner_name}'s GM doesn't see enough value. "
                    f"They're giving up {their_pts:.1f} PPG for your {my_pts:.1f} PPG — offer more."
                )
            else:
                st.success("✅ AI GM will accept this trade.")

            if st.button("📨 Propose Trade"):
                if accepted:
                    for name in my_names:
                        st.session_state.my_roster_overrides[name] = partner_team['id']
                    for name in their_names:
                        st.session_state.my_roster_overrides[name] = current_team_id
                    trade_str = (
                        f"Sent: {', '.join(my_names)}  →  "
                        f"Received: {', '.join(their_names)} (from {partner_name})"
                    )
                    st.session_state.trade_history.insert(0, trade_str)
                    # Hard mode: chemistry disruption penalty
                    if hard:
                        st.session_state.trade_cooldown = max(
                            st.session_state.get('trade_cooldown', 0), 5
                        )
                    save_state()
                    st.success(f"Trade complete! {trade_str}")
                    st.rerun()
                else:
                    st.error(f"❌ Rejected by {partner_name}'s GM.")

    if st.session_state.trade_history:
        with st.expander("Trade History"):
            for trade in st.session_state.trade_history[:10]:
                st.write(f"• {trade}")
