# Thulla — context for LLMs / bot work

## Goal

Build the **strongest Thulla bot we can**, measured mainly against a **random legal-move baseline** (`RandomPlayer`). Eval harness: `scripts/run_eval.py` (strength + P(thulla) calibration). Secondary: self-play vs `ComputerPlayer`.

This repo is an engine + web UI so humans can play the same rules the bots use. Policy lives in `thulla/players.py` + `thulla/prob.py` + `thulla/cards.py` (`raise_equivalence`); public state in `thulla/info.py`.

---

## Rules (as implemented)

**Deck / seats:** Standard 52 cards. **3–8** players. Hands dealt as evenly as possible. Rank in-suit: `2 < … < 10 < J < Q < K < A`. No trump.

**Objective:** Empty your hand and **get away**. Finishing order is recorded; the **last player with cards loses**.

### First trick

- Holder of **Ace of Spades** leads and **must** play AS.
- Led suit is Spades. Must follow if able.
- Off-suit on the first trick is allowed and is **not** a thulla (cards still discard if everyone finishes cleanly).



### Normal tricks

1. Leader plays any card → that suit is led.
2. Others must **follow suit if they can**.
3. If everyone follows: highest card of the led suit **wins**; pot is **discarded**; winner leads next.
4. If someone **cannot** follow and plays off-suit → **THULLA**: the player who currently holds the highest *led-suit* card **picks up the whole pot** into their hand and leads next.



### After a trick

- Anyone with **0 cards** gets away (in clockwise order from the check point).
- Then a **take phase** when **≥3** players remain (one clockwise pass from the current leader): each active player may ask the **next clockwise** neighbor for **all** of their cards. Neighbor may refuse. If accepted, asker takes the hand and the neighbor gets away. (Bot policy today: only the **leader** ever asks; victims usually give.)
- **Heads-up (2 left):** take phase is **disabled** — asking would just hand the opponent a win. Play continues until someone empties.

Game ends when ≤1 player still has cards.

---



## What the bot sees

Bots never see hidden hands. They get a `PlayerView` over `PublicInfo`:


| Hard facts                                | Soft hints (UI / future weights only — **not** used by bot policy or MC)                                                                                                                             |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Suit **voids** (failed to follow)         | Duck under leader → likely no **still-unknown** ranks strictly between play and ceiling (`duck_gap_unknowns`; skips discarded/trick/known)                                                           |
| **Discarded** clean-trick cards           | Took lead in-suit → likely no higher of that suit left (`suit_high_shown`)                                                                                                                           |
| **Known holdings** (thulla pickup / take) |                                                                                                                                                                                                      |
| Hand sizes, current trick / high          |                                                                                                                                                                                                      |
| **Heads-up complete info**                | With exactly 2 active, `deduced_hand` / `visible_cards` recover the opponent's full hand from deck − discarded − my hand − known − trick (**viewer-relative**; not written into shared `PublicInfo`) |


Sampling in `prob.py` must respect **hard** constraints (+ heads-up deduction) only. Soft duck / suit-high hints must not hard-ban deals.

---



## Current bot (baseline “smart”)

Not a search engine — heuristics + light Monte Carlo:

- Estimate **P(someone after me is void)** in a suit (~deal samples; default 200). Soft floor when a later seat ducked with a **keeper (2–5)** under a higher card (`KEEPER_DUCK_VOID_FLOOR`) — treat that suit as near-void for lead safety (not a hard void).
- **Dump tiers:** faces `A/K/Q/J` → mids `6–10` → keepers `2–5` (singleton / shorter suit bias on lead).
- Lead: among dump-safe suits (not long, not heavily discarded, no known/high void risk), pick highest tier preferring shorter holdings; never lead a keeper when any mid/face is legal. When multiple lead options remain, MC lose-rate lookahead runs while `free_unknowns ≤ LOOKAHEAD_MAX_UNKNOWN` (52 in code — effectively always during normal play); otherwise falls back to heuristic lead. MC shortlist caps candidates; keepers are not filtered out of the shortlist.
- Follow: cash best face/winner when void risk after you is low (`follow_take_safe` — void/`P(thulla)` only; length/discards do **not** block). Otherwise dump best under by tier. Hard-duck when void risk after you is high. No soft-duck sandbagging.
- **Equivalence raise** (`cards.raise_equivalence`): after any pick, always play the **highest** of that card’s same-suit equivalence class — continuous ranks, or gaps fully accounted (discards / known / trick / own hand). Prevents gifting a low undercutter via thulla (e.g. hold 4–8 → never play the 4 when the 8 is equivalent).
- Thulla dump: MC over a shortlist (≤4 cards); early/mid uses short-horizon away/shed only, late (≤20 unknowns) adds capped lose-rate rollouts. Sticky `away+shed` only when escape looks live (victim near empty or max away ≥ threshold); otherwise dump by liability (`faces > mids > keepers`). Dedicated sample budget (8–24), never the 200 void-estimate count. Ideal Move shows rates. Always `raise_equivalence` after the pick.
- Take: leader only, ≥3 active; take **only** when MC says merge clearly lowers P(finish last) (`unknowns ≤ 20`); case-A void/small-hand is a soft hint only. Stronger margin if a dump-safe face lead remains.

`RandomPlayer` = uniform random among legal moves (and never takes). That’s the primary strength baseline.

Ideal Move coach (`thulla/advise.py`) is the **same** policy for the human seat (structured steps), not a second brain.

---



## Game logs (for bot review)


| Path                          | Purpose     |
| ----------------------------- | ----------- |
| `games/ongoing/{human_vs_ai   | ai_vs_ai}/` |
| `games/completed/{human_vs_ai | ai_vs_ai}/` |


Completed / ongoing reviews include opening hands, trick-by-trick plays, takes, and Ideal Move snapshots (on human decisions + panel fetches). Prefer reading the `.md` for manual review.

---

