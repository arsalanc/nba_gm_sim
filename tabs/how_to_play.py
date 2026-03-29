import streamlit as st


def render():
    st.subheader("How to Play")
    st.caption("Everything you need to know to build a championship franchise.")

    with st.expander("🏀 Overview", expanded=True):
        st.markdown("""
**Goal:** Win the NBA Championship by managing your team through the regular season and playoffs.

1. **Pick your franchise** and choose a difficulty and season length on the start screen.
2. **Build your lineup** each game day — choose your 5 starters and a strategy.
3. **Simulate or play live** — batch-sim multiple games quickly, or play quarter-by-quarter with full control.
4. **Make trades** to improve your roster when needed.
5. **Finish top 8** in your conference to make the playoffs.
6. **Win 4 rounds** of best-of-7 playoff series to lift the trophy.
""")

    with st.expander("📝 Gameplan Tab"):
        st.markdown("""
**What it shows:**
- Your next opponent's projected lineup and overall rating.
- A **team strength bar** comparing your OVR to theirs.
- A **Scouting Report** with recommended strategy and the opponent's top scorer to watch.

During playoffs, it shows the current series score and round.
""")

    with st.expander("🏟️ Game Day Tab"):
        st.markdown("""
**Picking a Lineup:**
- Check up to **5 players** to start. The top 5 by PPG are pre-selected.
- Injured players are automatically excluded.
- The salary cap indicator warns you of cap violations (cosmetic only — no hard block).

**Strategy:**
| Strategy | Effect |
|----------|--------|
| Balanced | 1.0× your score, 1.0× opponent score |
| Pace & Space | 1.2× your score, 1.1× opponent score (high variance) |
| Grit & Grind | 0.9× your score, 0.8× opponent score (lower scores, tighter games) |

**Simulating Games:**
- **Sim 1 / Sim 5 / Sim 10** — fast-forward games instantly.
- **Play Live** — play quarter by quarter. Make subs between quarters and change strategy.

**During a Live Game:**
- Court view shows your 5 players with live stamina bars.
- Sub players out before their stamina drops too low.
- After Q4, if it's tied — **Overtime** is played automatically.

**After Each Game:**
- Box score shows stats for both teams (PTS, REB, AST, STL, BLK, TOV).
- **Game Flow chart** shows the score progression possession-by-possession (live games only).
""")

    with st.expander("📋 Trade Desk Tab"):
        st.markdown("""
**How Trades Work:**
- Pick a trade partner and select 1–3 players on each side.
- **Salary matching rule:** Incoming salary must be ≤ outgoing × 1.25 + $100K.
- The **AI GM evaluates value** — they won't accept a lopsided deal (their PPG must be ≤ your PPG × threshold).

**Hard Mode:** Trades trigger a **5-game chemistry penalty** (-5% scoring) after a deal is made.

**Trade Cooldown** is shown in the sidebar when active.
""")

    with st.expander("🏆 Standings Tab"):
        st.markdown("""
- Shows **W/L record, win%, and GB** for all 30 teams split by conference.
- A divider marks the **playoff cutoff** at #8 in each conference.
- After game {season_length}, standings lock and the bracket is generated automatically.
- If you **make the playoffs**, the bracket tab populates and your first-round opponent is set.
- If you **miss the playoffs**, you can spectate and simulate the remaining rounds.
""")

    with st.expander("🏀 Bracket Tab"):
        st.markdown("""
- Shows the full playoff bracket: **West on the left, Finals in the center, East on the right**.
- Your team is highlighted in **blue**.
- Series wins are shown on each matchup box.
- The bracket updates live as rounds are completed.
""")

    with st.expander("💡 Tips & Strategy"):
        st.markdown("""
**Injuries:**
- Players with low stamina are more likely to get injured.
- Injured players appear in the **Medical Report** in the sidebar and are automatically benched.
- Injury timers count down by 1 each game played.

**Stamina (Hard Mode only):**
- Stamina carries over between games. Starters who played heavy minutes will be fatigued next game.
- Bench players recover faster. Rotate your roster across a long season.

**Difficulty Differences:**

| Feature | Easy | Hard |
|---------|------|------|
| Opponent stamina | 55–100% | 85–100% |
| Tactic advantage | Full | Neutral |
| Injury frequency | Lower | Higher |
| Stamina carryover | No | Yes |
| Trade threshold | 1.15× PPG | 1.05× PPG |
| Trade chemistry penalty | No | 5 games |

**Overtime:**
- If a game ends tied after Q4, overtime periods are played until there's a winner.

**Season Length:**
- Shorter seasons (20 or 41 games) reach playoffs faster but give less time to develop standings.
""")
