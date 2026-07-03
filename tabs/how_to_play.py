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
- **Defense matters:** your starters' combined steals + blocks (🛡️ "stocks") suppress the
  opponent's score in sims. Sometimes a two-way player beats a slightly higher scorer.
- The salary cap indicator warns you of cap violations (cosmetic only — no hard block).

**Strategy — pace vs. variance:**
| Strategy | Pace | Scores | Variance | Best when... |
|----------|------|--------|----------|--------------|
| Balanced | Normal | Normal | Normal | It's a coin-flip matchup |
| Pace & Space | Fast | High | **Low** — talent wins out | You're the **favorite** (costs more stamina) |
| Grit & Grind | Slow | Low | **High** — anything can happen | You're the **underdog** |

This mirrors real NBA analytics: underdogs shorten the game, favorites want more possessions.

**Simulating Games:**
- **Sim 1 Game** — instantly sim the next game with your chosen lineup and strategy.
- **Fast Forward** — sim 5 or 10 games, or jump to a milestone: the **trade deadline**
  or the **end of the regular season**. Your lineup plays the first game, then the best
  healthy five is auto-picked. An injury digest shows everything that happened.
- **Play Live** — play quarter by quarter. Make subs between quarters and change strategy.

**During a Live Game:**
- Court view shows your 5 players with live stamina bars.
- Sub players out before their stamina drops too low.
- **🔥 Clutch time:** in Q4/OT within 5 points, stars take over the offense.
- After Q4, if it's tied — **Overtime** is played automatically.

**After Each Game:**
- A **headline** and **Player of the Game** sum up the result.
- Box score shows stats for both teams (PTS, REB, AST, STL, BLK, TOV).
- **Game Flow chart** shows the score progression possession-by-possession (live games only).
""")

    with st.expander("📋 Trade Desk Tab"):
        st.markdown("""
**How Trades Work:**
- Pick a trade partner and select 1–3 players on each side.
- **Salary matching rule:** Incoming salary must be ≤ outgoing × 1.25 + $100K.
- **🚨 Luxury-tax apron:** if your payroll is over the tax line, matching tightens
  to × 1.10 — big consolidation trades get much harder until you shed salary.
- The **AI GM evaluates trade value**, which scales superlinearly with OVERALL —
  **stars carry a premium**. One 90 OVR ≈ three 75 OVRs, so you can't package
  role players into a superstar.
- Trades are **league-wide**: players you send away actually join their new team
  and play against you; players you acquire leave their old roster.

**⏳ Trade Deadline:** Trading closes **75% of the way through the season** (game 61
of 82), and rosters are locked during the playoffs — build your contender early.

**Hard Mode:** Trades trigger a **5-game chemistry penalty** (-5% scoring) after a deal is made.

**Trade Cooldown** is shown in the sidebar when active.
""")

    with st.expander("🏆 Standings Tab"):
        st.markdown("""
- Shows **W/L record, win%, and GB** for all 30 teams split by conference.
- A divider marks the **playoff cutoff** at #8 in each conference.
- After the final regular-season game, standings lock and the bracket is generated automatically.
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

    with st.expander("🏛️ Franchise Mode (multi-season)"):
        st.markdown("""
Enable **Franchise Mode** on the start screen to play season after season with a living league.

**After each championship**, the offseason runs:
1. **Aging & retirements** — young players improve (peak ~27), veterans decline after 30,
   and aging players retire. The Offseason Report shows the biggest risers, decliners, and farewells.
2. **Draft lottery** — the 14 worst teams enter a weighted lottery for the top 4 picks;
   the rest of the order follows reverse standings.
3. **The draft** — one round, 30 picks, from a class of generated prospects.

**Scouting the draft:**
- Each prospect shows position, archetype, age, **current OVR**, and a **potential grade**
  (A+ to C) with a projected range — but the true ceiling is **hidden**.
- Younger prospects have higher upside *and* higher bust risk.
- Late picks can outplay lottery picks — that's the fun.

**💰 Salary cap economics:**
- Salaries track production, so an improving young roster gets **more expensive every season**.
- The **cap and tax lines grow 8% per season** (like the real NBA), absorbing normal growth.
- Over the cap but under the tax = fine (soft cap). Over the **luxury tax** = apron
  trade restrictions until you shed payroll.

Your trades and draft picks **carry over between seasons** — the roster you build is the long game.
Turn Franchise Mode off for a single-season run that always resets to the real NBA.
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

**💤 Load Management (Hard Mode only):**
- In the Game Day tab, the **Load Management** panel lets you rest players for the next game.
- A rested player **sits out entirely, recovers to 100% stamina, and can't be injured** that game — but you play short-handed.
- To rest a starter, uncheck them from your lineup first, then mark them to rest.
- The panel warns you when a starter is gassed (low stamina = higher injury risk).

**🏠 Home Court & 🔥 Momentum:**
- Games alternate **home and away**. Home court is worth **+2% scoring**; road games cost **-2%**.
  Check the Gameplan tab or Game Day header to see where you're playing.
- Win **3+ in a row** and your team catches fire: **+1% scoring per streak game, up to +5%**.
  The sidebar shows your active streak. Protect it — a loss resets everything.

**Difficulty Differences:**

| Feature | Easy | Hard |
|---------|------|------|
| Opponent intensity | 80–100% | 90–100% |
| Injury frequency | Lower | Higher |
| Stamina carryover | No | Yes |
| AI GM trade demands | Lenient (−10% ok) | Near-even value |
| Trade chemistry penalty | No | 5 games |
| Opponent comeback push (live) | No | Yes |

**Playoffs:**
- 🔥 **Playoff intensity** — opponents play near full strength in the postseason
  (Easy: 86–100%, Hard: 95–100%). Regular-season cruise control won't work.

**Overtime:**
- If a game ends tied after Q4, overtime periods are played until there's a winner.

**Season Length:**
- Shorter seasons (20 or 41 games) reach playoffs faster but give less time to develop standings.
- **🏆 Playoffs Only** sims the entire regular season the moment you sign — you jump straight
  into the bracket. If your team would have missed the cut, they sneak in as the **#8 seed**
  for an underdog run. Rosters are locked (no trades), so it's pure playoff basketball.
""")
