import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from utils import player_img_url, team_logo_url, fmt_salary


def render(all_stats, w, l, all_teams, roster=None, my_team=None):
    st.subheader("Season Statistics")
    st.write(f"**Games played:** {len(st.session_state.results)} | **Record:** {w}W — {l}L")

    # ── Team MVP — the player carrying your team this season ───────────────────
    if st.session_state.season_pts:
        mvp_name, mvp_pts = max(st.session_state.season_pts.items(), key=lambda kv: kv[1])
        mvp_row = all_stats[all_stats['PLAYER'] == mvp_name]
        games = max(len(st.session_state.results), 1)
        st.markdown("#### 🏅 Team MVP")
        mc = st.columns([1, 5])
        if not mvp_row.empty:
            mc[0].image(player_img_url(int(mvp_row.iloc[0]['PLAYER_ID'])), width=70)
        mc[1].markdown(
            f"**{mvp_name}** — {mvp_pts} total points "
            f"(**{mvp_pts / games:.1f}** per game across {games} games)"
        )
        st.divider()

    if st.session_state.season_pts:
        df_leader = (
            pd.DataFrame(
                st.session_state.season_pts.items(),
                columns=['Player', 'Total Points']
            )
            .sort_values('Total Points', ascending=False)
            .merge(all_stats[['PLAYER', 'PLAYER_ID']], left_on='Player', right_on='PLAYER', how='left')
        )

        hdr = st.columns([1, 4, 2])
        hdr[1].write("**Player**")
        hdr[2].write("**Season Points**")
        st.divider()
        for _, row in df_leader.head(15).iterrows():
            rc = st.columns([1, 4, 2])
            if pd.notna(row.get('PLAYER_ID')):
                rc[0].image(player_img_url(int(row['PLAYER_ID'])), width=45)
            rc[1].write(f"**{row['Player']}**")
            rc[2].write(f"{int(row['Total Points'])} pts")
    else:
        st.info("Play some games to see season stats here.")

    # ── Win % Trend ───────────────────────────────────────────────────────────
    results = st.session_state.results
    if len(results) >= 5:
        st.divider()
        st.subheader("📈 Win % Trend")
        win_pct = []
        for i in range(1, len(results) + 1):
            wins = results[:i].count('W')
            win_pct.append(round(wins / i, 3))
        st.line_chart(win_pct)
        st.caption("Rolling win percentage over the season.")

    # ── League Leader Boards ──────────────────────────────────────────────────
    st.divider()
    st.subheader("📊 League Leader Boards")

    team_abbr_map = {t['id']: t['abbreviation'] for t in all_teams}

    def _leader_table(stat_col, label, n=10):
        top = (
            all_stats[['PLAYER', 'PLAYER_ID', 'TEAM_ID', stat_col]]
            .dropna(subset=[stat_col])
            .sort_values(stat_col, ascending=False)
            .head(n)
            .reset_index(drop=True)
        )
        hdr = st.columns([1, 1, 4, 2, 2])
        hdr[0].write("**#**")
        hdr[1].write("")
        hdr[2].write("**Player**")
        hdr[3].write("**Team**")
        hdr[4].write(f"**{label}**")
        st.divider()
        for rank, row in top.iterrows():
            rc = st.columns([1, 1, 4, 2, 2])
            rc[0].write(f"{rank + 1}")
            pid = int(row['PLAYER_ID'])
            if pid:
                rc[1].image(player_img_url(pid), width=35)
            rc[2].write(row['PLAYER'])
            tid = int(row['TEAM_ID'])
            abbr = team_abbr_map.get(tid, '?')
            logo_col, abbr_col = rc[3].columns([1, 2])
            logo_col.image(team_logo_url(tid), width=25)
            abbr_col.write(abbr)
            rc[4].write(f"**{row[stat_col]:.1f}**")

    lb_pts, lb_reb, lb_ast = st.tabs(["🏀 Points", "💪 Rebounds", "🎯 Assists"])
    with lb_pts:
        _leader_table('PTS', 'PPG')
    with lb_reb:
        _leader_table('REB', 'RPG')
    with lb_ast:
        _leader_table('AST', 'APG')

    # ── Salary vs. Performance — spot overpaid players & trade targets ────────
    if roster is not None and not roster.empty and 'OVERALL' in roster.columns:
        st.divider()
        st.subheader("💰 Roster Value Map")
        st.caption("Each bubble is a player on your roster — X = salary, Y = overall rating, "
                   "size = PPG. Players **below the line** are overpaid; **above it** are bargains.")

        rdf = roster.copy()
        rdf['SAL_M'] = rdf['SALARY'] / 1_000_000

        # Fair-value reference line: league relationship between salary and OVR
        league = all_stats.copy()
        league['SAL_M'] = league['SALARY'] / 1_000_000
        if league['SAL_M'].std() > 1e-6:
            slope, intercept = np.polyfit(league['SAL_M'], league['OVERALL'], 1)
        else:
            slope, intercept = 0.0, league['OVERALL'].mean()

        rdf['fair_ovr'] = slope * rdf['SAL_M'] + intercept
        rdf['verdict'] = rdf.apply(
            lambda r: 'Bargain' if r['OVERALL'] >= r['fair_ovr'] + 2
            else 'Overpaid' if r['OVERALL'] <= r['fair_ovr'] - 2 else 'Fair', axis=1)
        color_map = {'Bargain': '#52b052', 'Fair': '#f0c040', 'Overpaid': '#e05252'}

        fig = go.Figure()
        for verdict, grp in rdf.groupby('verdict'):
            fig.add_trace(go.Scatter(
                x=grp['SAL_M'], y=grp['OVERALL'],
                mode='markers+text',
                name=verdict,
                marker=dict(
                    size=(grp['PTS'].clip(lower=1)) * 2.2,
                    color=color_map.get(verdict, '#888'),
                    line=dict(width=1, color='white'), opacity=0.8,
                ),
                text=grp['PLAYER'].apply(lambda s: s.split()[-1]),
                textposition='top center',
                textfont=dict(size=10, color='white'),
                customdata=grp[['PLAYER', 'PTS']].values,
                hovertemplate='%{customdata[0]}<br>$%{x:.1f}M · OVR %{y}<br>%{customdata[1]:.1f} PPG<extra></extra>',
            ))
        xline = [rdf['SAL_M'].min(), rdf['SAL_M'].max()]
        fig.add_trace(go.Scatter(
            x=xline, y=[slope * x + intercept for x in xline],
            mode='lines', name='Fair value',
            line=dict(color='rgba(255,255,255,0.4)', width=2, dash='dash'),
            hoverinfo='skip',
        ))
        fig.update_layout(
            plot_bgcolor='#0e1117', paper_bgcolor='#0e1117', font=dict(color='white'),
            xaxis=dict(title='Salary ($M)'), yaxis=dict(title='Overall rating'),
            margin=dict(l=40, r=20, t=20, b=40), height=420,
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

        overpaid = rdf[rdf['verdict'] == 'Overpaid'].sort_values('SALARY', ascending=False)
        if not overpaid.empty:
            worst = overpaid.iloc[0]
            st.caption(f"🔎 Trade-block candidate: **{worst['PLAYER']}** "
                       f"({fmt_salary(worst['SALARY'])}, OVR {int(worst['OVERALL'])}, "
                       f"{worst['PTS']:.1f} PPG) is your most overpaid player.")
