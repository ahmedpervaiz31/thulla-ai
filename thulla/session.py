"""Step-based game session for the web UI (no blocking game_loop / input)."""

from __future__ import annotations

import uuid
from typing import Any

from .cards import parse_card, valid_moves
from .game import ThullaGame, TrickState
from .players import BasePlayer, ComputerPlayer, choose_computer_card
from .review import compact_advice, new_review


class InteractiveSeat(BasePlayer):
    """Human seat for the web session — never calls input()."""

    def play_turn(self, expected_cards, view=None):
        raise RuntimeError("InteractiveSeat must not be driven via play_turn; use GameSession")

    def offer_take(self, target_name, n_cards, view=None, neighbor_idx=None, i_am_leader=False):
        raise RuntimeError("InteractiveSeat must not be driven via offer_take; use GameSession")

    def offer_give(self, asker_name, n_cards, view=None, asker_idx=None):
        raise RuntimeError("InteractiveSeat must not be driven via offer_give; use GameSession")


class GameSession:
    """
    Drives Thulla one decision at a time.

    Phases: first_trick | take | trick | finished
    """

    def __init__(
        self,
        mode: str,
        player_count: int,
        game_id: str | None = None,
        *,
        deal: bool = True,
    ):
        if mode not in ("human", "ai"):
            raise ValueError("mode must be 'human' or 'ai'")
        if player_count < 3 or player_count > 8:
            raise ValueError("player count must be between 3 and 8")

        self.id = game_id or str(uuid.uuid4())
        self.mode = mode
        self.human_seat = 0 if mode == "human" else None

        if mode == "human":
            players = [InteractiveSeat("You")]
            for i in range(1, player_count):
                players.append(ComputerPlayer(f"CPU{i}"))
        else:
            players = [ComputerPlayer(f"CPU{i}") for i in range(1, player_count + 1)]

        self.game = ThullaGame(players, verbose=False)
        self.phase = "first_trick"
        self.leader: int | None = None
        self.trick: TrickState | None = None
        self.take_queue: list[int] = []
        self.take_leader: int | None = None
        self.pending: dict[str, Any] | None = None
        self.last_event: str | None = None
        self.status = "Starting"
        self.event_log: list[dict[str, Any]] = []
        self.review: dict[str, Any] = new_review(mode, [p.name for p in players])
        self._review_trick: dict[str, Any] | None = None
        self.last_advice: dict[str, Any] | None = None

        if deal:
            self.game.shuffle_and_deal()
            self.review["opening_hands"] = [
                [c.code() for c in p.hand] for p in self.game.players
            ]
            self.leader = self.game.ace_spades_holder_idx
            self._start_trick(first_trick=True)
        # Client paces CPU plays via /step (see trick_reveal for readable pot).

    def is_human(self, seat: int) -> bool:
        return self.human_seat is not None and seat == self.human_seat

    def _start_trick(self, first_trick: bool):
        self.phase = "first_trick" if first_trick else "trick"
        self.trick = self.game.begin_trick(self.leader, first_trick=first_trick)
        if self.trick is None:
            self._finish_game()
            return
        self.status = f"Trick {self.game.trick_number}"
        self.pending = None
        self._begin_review_trick()
        self._set_play_pending_or_none()

    def _begin_review_trick(self):
        assert self.trick is not None
        self._review_trick = {
            "n": self.game.trick_number,
            "leader": self.game.players[self.trick.leader_idx].name,
            "leader_seat": self.trick.leader_idx,
            "first_trick": self.trick.first_trick,
            "plays": [],
        }

    def _snapshot_advice_for_pending(self) -> dict[str, Any] | None:
        """Ideal Move for the human seat when it is their decision."""
        if self.mode != "human" or self.pending is None:
            return None
        seat = self.pending.get("seat")
        if seat is None or not self.is_human(seat):
            return None
        if self.pending.get("type") not in ("play", "take", "give"):
            return None
        from .advise import advise_session

        return compact_advice(advise_session(self))

    def _log_play(
        self,
        seat: int,
        card,
        *,
        hand_before: list[str],
        legal: list[str],
        advice: dict[str, Any] | None = None,
    ):
        if self._review_trick is None:
            self._begin_review_trick()
        assert self.trick is not None and self._review_trick is not None
        expected = self.game.expected_for_seat(self.trick, seat)
        hand_cards = [parse_card(c) for c in hand_before]
        hand_cards = [c for c in hand_cards if c is not None]
        must_follow = bool(expected) and any(c in expected for c in hand_cards)
        if expected is None:
            kind = "lead"
        elif must_follow:
            kind = "follow"
        else:
            kind = "thulla"
        highest = self.trick.highest_card
        entry: dict[str, Any] = {
            "seat": seat,
            "name": self.game.players[seat].name,
            "card": card.code(),
            "kind": kind,
            "human": self.is_human(seat),
            "hand_before": list(hand_before),
            "legal": list(legal),
            "lead_suit": self.trick.colour,
            "current_highest": highest.code() if highest else None,
        }
        if advice:
            entry["advice"] = advice
            rec = advice.get("recommended") or {}
            if isinstance(rec, dict) and rec.get("card"):
                entry["followed_advice"] = rec["card"] == card.code()
        self._review_trick["plays"].append(entry)

    def _finalize_review_trick(self):
        if self._review_trick is None or self.trick is None:
            return
        pot = [c.code() for c in self.trick.stack]
        self._review_trick["pot"] = pot
        if self.trick.result == "thulla":
            self._review_trick["result"] = "thulla"
            self._review_trick["victim"] = self.game.players[self.trick.highest_idx].name
            self._review_trick["victim_seat"] = self.trick.highest_idx
        else:
            self._review_trick["result"] = "win"
            self._review_trick["winner"] = self.game.players[self.trick.highest_idx].name
            self._review_trick["winner_seat"] = self.trick.highest_idx
        self.review.setdefault("tricks", []).append(self._review_trick)
        self._review_trick = None

    def _log_take(
        self,
        asker: int,
        target: int,
        given: bool,
        n_cards: int,
        *,
        advice: dict[str, Any] | None = None,
        human_decision: str | None = None,
    ):
        entry: dict[str, Any] = {
            "after_trick": self.game.trick_number,
            "asker": self.game.players[asker].name,
            "asker_seat": asker,
            "target": self.game.players[target].name,
            "target_seat": target,
            "n_cards": n_cards,
            "given": given,
        }
        if human_decision:
            entry["human_decision"] = human_decision
        if advice:
            entry["advice"] = advice
            rec = advice.get("recommended") or {}
            if isinstance(rec, dict) and "accept" in rec:
                if human_decision == "ask":
                    entry["followed_advice"] = bool(rec["accept"]) is True
                elif human_decision == "decline_ask":
                    entry["followed_advice"] = bool(rec["accept"]) is False
                elif human_decision == "give":
                    entry["followed_advice"] = bool(rec["accept"]) is True
                elif human_decision == "refuse":
                    entry["followed_advice"] = bool(rec["accept"]) is False
        self.review.setdefault("takes", []).append(entry)

    def record_advice_request(self, advice: dict[str, Any]):
        """Persist an Ideal Move fetch (human mode coach panel)."""
        compact = compact_advice(advice)
        self.last_advice = compact
        if compact is None:
            return
        self.review.setdefault("advice_requests", []).append(
            {
                "trick_number": self.game.trick_number,
                "phase": self.phase,
                "pending": (self.pending or {}).get("type"),
                "advice": compact,
            }
        )

    def _set_play_pending_or_none(self):
        if self.trick is None or self.trick.done:
            self.pending = None
            return
        seat = self.trick.order[self.trick.seat_pos]
        expected = self.game.expected_for_seat(self.trick, seat)
        hand = self.game.players[seat].hand
        legal = [c.code() for c in valid_moves(hand, expected)]
        lead = self.trick.colour
        self.pending = {
            "type": "play",
            "seat": seat,
            "legal": legal,
            "lead_suit": lead,
            "first_trick": self.trick.first_trick,
            "must_follow": bool(expected) and any(c in expected for c in hand),
        }

    def _enter_trick_reveal(self):
        """Keep the finished pot visible until the client steps past it."""
        assert self.trick is not None and self.trick.done
        self._finalize_review_trick()
        if self.trick.result == "thulla":
            victim = self.game.players[self.trick.highest_idx].name
            self.last_event = f"THULLA! {victim} picks up the pot"
        else:
            winner = self.game.players[self.trick.highest_idx].name
            self.last_event = f"{winner} wins the trick"
        was_first = self.trick.first_trick
        self._reveal_was_first = was_first
        self._reveal_next_leader = self.trick.next_leader
        self.phase = "trick_reveal"
        self.status = "Trick result"
        self.pending = {"type": "reveal"}

    def _after_trick(self):
        """Clear the revealed pot and continue into take / next trick / finish."""
        assert self.trick is not None
        next_leader = getattr(self, "_reveal_next_leader", self.trick.next_leader)
        was_first = getattr(self, "_reveal_was_first", self.trick.first_trick)
        self.trick = None
        self.pending = None

        check_from = self.game.ace_spades_holder_idx if was_first else next_leader
        self.leader = self.game.check_got_away(check_from)

        if len(self.game.active_player_indices) <= 1:
            self._finish_game()
            return

        self._begin_take_pass()

    def _begin_take_pass(self):
        self.leader = self.game.ensure_leader_active(self.leader)
        if self.leader is None or len(self.game.active_player_indices) <= 1:
            self._finish_game()
            return
        # Heads-up: skip neighbor-take prompts; continue playing.
        if len(self.game.active_player_indices) <= 2:
            self._start_trick(first_trick=False)
            return
        self.phase = "take"
        self.take_leader = self.leader
        self.take_queue = list(self.game.active_in_order(self.leader))
        self.status = f"Take phase (lead {self.game.players[self.leader].name})"
        self.pending = None
        self._set_take_pending_or_advance()

    def _set_take_pending_or_advance(self):
        while self.take_queue:
            if len(self.game.active_player_indices) <= 1:
                self._finish_game()
                return
            idx = self.take_queue[0]
            if idx not in self.game.active_player_indices:
                self.take_queue.pop(0)
                continue
            ctx = self.game.take_offer_context(self.take_leader, idx)
            if ctx is None:
                self.take_queue.pop(0)
                continue
            target, n_cards, _view = ctx
            self.pending = {
                "type": "take",
                "seat": idx,
                "target": target,
                "target_name": self.game.players[target].name,
                "n_cards": n_cards,
                "i_am_leader": idx == self.take_leader,
            }
            return

        # Take pass done → next trick
        self.leader = self.game.ensure_leader_active(self.take_leader)
        self.take_queue = []
        if self.leader is None or len(self.game.active_player_indices) <= 1:
            self._finish_game()
            return
        self._start_trick(first_trick=False)

    def _finish_game(self):
        self.phase = "finished"
        self.pending = None
        self.trick = None
        self.status = "Game over"
        self.last_event = "Game over"

    def _play_cpu_card(self, seat: int) -> str:
        assert self.trick is not None
        player = self.game.players[seat]
        if isinstance(player, InteractiveSeat):
            raise RuntimeError("cannot auto-play interactive seat")
        expected = self.game.expected_for_seat(self.trick, seat)
        view = self.game.view_for_seat(self.trick, seat)
        hand_before = [c.code() for c in player.hand]
        legal = [c.code() for c in valid_moves(player.hand, expected)]
        if isinstance(player, ComputerPlayer):
            moves = valid_moves(player.hand, expected)
            card = choose_computer_card(
                player.hand, moves, expected, view, samples=player.mc_samples
            )
        else:
            # ScriptedPlayer / RandomPlayer: play_turn may already remove the card
            card = player.play_turn(expected, view)
        self._log_play(seat, card, hand_before=hand_before, legal=legal)
        return self.game.apply_play(self.trick, seat, card)

    def _decide_cpu_take(self, seat: int) -> bool:
        assert self.pending and self.pending["type"] == "take"
        player = self.game.players[seat]
        target = self.pending["target"]
        n_cards = self.pending["n_cards"]
        ctx = self.game.take_offer_context(self.take_leader, seat)
        view = ctx[2] if ctx else None
        return bool(
            player.offer_take(
                self.game.players[target].name,
                n_cards,
                view=view,
                neighbor_idx=target,
                i_am_leader=self.pending["i_am_leader"],
            )
        )

    def _decide_cpu_give(self, seat: int) -> bool:
        assert self.pending and self.pending["type"] == "give"
        player = self.game.players[seat]
        asker = self.pending["asker"]
        n_cards = self.pending["n_cards"]
        remaining = [p for p in self.game.active_in_order(seat) if p != seat]
        self.game.info.sync_hands(self.game.players)
        view = self.game.info.view_for(seat, remaining)
        return bool(
            player.offer_give(
                self.game.players[asker].name,
                n_cards,
                view=view,
                asker_idx=asker,
            )
        )

    def _set_give_pending(self, asker: int, target: int, n_cards: int):
        self.pending = {
            "type": "give",
            "seat": target,
            "asker": asker,
            "asker_name": self.game.players[asker].name,
            "n_cards": n_cards,
        }

    def _pop_take_seat(self, seat: int):
        if self.take_queue and self.take_queue[0] == seat:
            self.take_queue.pop(0)
        elif seat in self.take_queue:
            self.take_queue.remove(seat)

    def step(self) -> dict:
        """Execute one CPU decision or dismiss a trick reveal. Raises if human input required."""
        if self.phase == "finished":
            return self.to_dict()
        if self.pending is None:
            return self.to_dict()

        if self.pending["type"] == "reveal":
            self._after_trick()
            return self.to_dict()

        seat = self.pending["seat"]
        if self.is_human(seat):
            raise RuntimeError("waiting for human input")

        if self.pending["type"] == "play":
            result = self._play_cpu_card(seat)
            if result != "continue":
                self._enter_trick_reveal()
            else:
                self._set_play_pending_or_none()
        elif self.pending["type"] == "take":
            accept = self._decide_cpu_take(seat)
            self._resolve_take_ask(seat, accept)
        elif self.pending["type"] == "give":
            accept = self._decide_cpu_give(seat)
            self._resolve_give(seat, accept)
        return self.to_dict()

    def advance_until_input(self) -> dict:
        """Run CPU/reveal steps until human must act, or game ends. Skips in AI mode."""
        guard = 0
        while self.phase != "finished" and self.pending is not None:
            if self.pending["type"] == "reveal":
                if self.mode == "ai":
                    break
                self.step()
            elif self.is_human(self.pending["seat"]):
                break
            elif self.mode == "ai":
                break
            else:
                self.step()
            guard += 1
            if guard > 500:
                raise RuntimeError("advance loop exceeded safety limit")
        return self.to_dict()

    def play_card(self, card_code: str) -> dict:
        if not self.pending or self.pending["type"] != "play":
            raise RuntimeError("not awaiting a card play")
        seat = self.pending["seat"]
        if not self.is_human(seat):
            raise RuntimeError("not human's turn to play")
        card = parse_card(card_code)
        if card is None:
            raise ValueError(f"invalid card code: {card_code}")
        if card.code() not in self.pending["legal"]:
            raise ValueError(f"illegal card {card.code()}; legal: {self.pending['legal']}")

        assert self.trick is not None
        hand_before = [c.code() for c in self.game.players[seat].hand]
        legal = list(self.pending["legal"])
        advice = self._snapshot_advice_for_pending()
        self.last_advice = advice
        self._log_play(
            seat, card, hand_before=hand_before, legal=legal, advice=advice
        )
        result = self.game.apply_play(self.trick, seat, card)
        if result != "continue":
            self._enter_trick_reveal()
        else:
            self._set_play_pending_or_none()
        # Do not auto-run CPUs here — client paces /step so plays are visible.
        return self.to_dict()

    def answer_take(self, accept: bool) -> dict:
        if not self.pending or self.pending["type"] != "take":
            raise RuntimeError("not awaiting a take decision")
        seat = self.pending["seat"]
        if not self.is_human(seat):
            raise RuntimeError("not human's turn to take")
        advice = self._snapshot_advice_for_pending()
        self.last_advice = advice
        self._resolve_take_ask(
            seat,
            accept,
            advice=advice,
            human_decision="ask" if accept else "decline_ask",
        )
        return self.to_dict()

    def answer_give(self, accept: bool) -> dict:
        if not self.pending or self.pending["type"] != "give":
            raise RuntimeError("not awaiting a give decision")
        seat = self.pending["seat"]
        if not self.is_human(seat):
            raise RuntimeError("not human's turn to give")
        advice = self._snapshot_advice_for_pending()
        self.last_advice = advice
        self._resolve_give(
            seat,
            accept,
            advice=advice,
            human_decision="give" if accept else "refuse",
        )
        return self.to_dict()

    def _resolve_take_ask(
        self,
        seat: int,
        accept: bool,
        *,
        advice: dict[str, Any] | None = None,
        human_decision: str | None = None,
    ):
        """Asker chose whether to request neighbor's cards."""
        if not accept:
            target = self.pending["target"]
            n_cards = self.pending["n_cards"]
            self._log_take(
                seat,
                target,
                False,
                n_cards,
                advice=advice,
                human_decision=human_decision,
            )
            self._pop_take_seat(seat)
            self.pending = None
            if len(self.game.active_player_indices) <= 1:
                self._finish_game()
                return
            self._set_take_pending_or_advance()
            return

        target = self.pending["target"]
        n_cards = self.pending["n_cards"]
        if self.is_human(target):
            self._set_give_pending(seat, target, n_cards)
            return

        # CPU / scripted victim consents immediately
        remaining = [p for p in self.game.active_in_order(target) if p != target]
        self.game.info.sync_hands(self.game.players)
        view = self.game.info.view_for(target, remaining)
        gives = bool(
            self.game.players[target].offer_give(
                self.game.players[seat].name,
                n_cards,
                view=view,
                asker_idx=seat,
            )
        )
        self._complete_take(
            seat,
            target,
            gives,
            advice=advice,
            human_decision=human_decision,
        )

    def _resolve_give(
        self,
        seat: int,
        accept: bool,
        *,
        advice: dict[str, Any] | None = None,
        human_decision: str | None = None,
    ):
        """Victim chose whether to hand over cards."""
        asker = self.pending["asker"]
        if not accept:
            self.last_event = (
                f"{self.game.players[seat].name} refuses "
                f"{self.game.players[asker].name}"
            )
        self._complete_take(
            asker,
            seat,
            accept,
            advice=advice,
            human_decision=human_decision,
        )

    def _complete_take(
        self,
        asker: int,
        target: int,
        given: bool,
        *,
        advice: dict[str, Any] | None = None,
        human_decision: str | None = None,
    ):
        n = len(self.game.players[target].hand)
        if given:
            self.last_event = (
                f"{self.game.players[asker].name} takes "
                f"{self.game.players[target].name}'s {n} cards"
            )
            self.game.apply_take(self.take_leader, asker, True)
        else:
            if not self.last_event or "refuses" not in (self.last_event or ""):
                self.last_event = (
                    f"{self.game.players[target].name} refuses "
                    f"{self.game.players[asker].name}"
                )
            self.game.apply_take(self.take_leader, asker, False)

        self._log_take(
            asker,
            target,
            given,
            n,
            advice=advice,
            human_decision=human_decision,
        )
        self._pop_take_seat(asker)
        self.pending = None
        if len(self.game.active_player_indices) <= 1:
            self._finish_game()
            return
        self._set_take_pending_or_advance()

    def to_dict(self) -> dict:
        g = self.game
        seats = []
        place_by_idx = {}
        for place, p in enumerate(g.winners, start=1):
            for i, pl in enumerate(g.players):
                if pl is p:
                    place_by_idx[i] = place

        for i, p in enumerate(g.players):
            active = i in g.active_player_indices
            entry = {
                "seat": i,
                "name": p.name,
                "hand_size": len(p.hand),
                "active": active,
                "place": place_by_idx.get(i),
                "is_human": self.is_human(i),
            }
            seats.append(entry)

        your_hand = None
        legal = None
        if self.human_seat is not None:
            your_hand = [c.code() for c in g.players[self.human_seat].hand]
            if self.pending and self.pending.get("type") == "play" and self.pending["seat"] == self.human_seat:
                legal = list(self.pending["legal"])

        trick_cards = []
        lead_suit = None
        if self.trick is not None:
            lead_suit = self.trick.colour
            for name, card in self.trick.plays:
                trick_cards.append({"player": name, "card": card.code()})

        winners = [{"place": i + 1, "name": p.name} for i, p in enumerate(g.winners)]
        loser = None
        leftover = g.remaining_players()
        if self.phase == "finished" and leftover:
            loser = leftover[0].name

        whose_turn = None
        if self.pending and self.pending.get("type") in ("play", "take", "give"):
            whose_turn = self.pending["seat"]

        # Lazy import: persist imports GameSession.
        from .persist import info_to_dict

        public = info_to_dict(g.info)
        # Viewer-relative heads-up deduction for the human scratch pad / bots
        # already use PlayerView.deduced_hand — do not write into shared PublicInfo.
        if self.human_seat is not None:
            g.info.sync_hands(g.players)
            remaining = [p for p in g.active_player_indices if p != self.human_seat]
            view = g.info.view_for(self.human_seat, remaining)
            my_hand = g.players[self.human_seat].hand
            deduced_seats = []
            for p in view.active_indices:
                if p == self.human_seat:
                    continue
                full = view.deduced_hand(p, my_hand)
                if full is None:
                    continue
                public["known_holdings"][str(p)] = sorted(c.code() for c in full)
                deduced_seats.append(p)
            if deduced_seats:
                public["complete_info"] = True
                public["deduced_seats"] = deduced_seats

        return {
            "id": self.id,
            "mode": self.mode,
            "phase": self.phase,
            "status": self.status,
            "trick_number": g.trick_number,
            "leader": self.leader,
            "whose_turn": whose_turn,
            "seats": seats,
            "trick": {
                "lead_suit": lead_suit,
                "cards": trick_cards,
                "first_trick": self.trick.first_trick if self.trick else False,
            },
            "pending": self.pending,
            "your_hand": your_hand,
            "legal_moves": legal,
            "winners": winners,
            "loser": loser,
            "last_event": self.last_event,
            "finished": self.phase == "finished",
            "public_info": public,
        }


# In-memory store for the web app
SESSIONS: dict[str, GameSession] = {}


def create_session(mode: str, players: int) -> GameSession:
    session = GameSession(mode, players)
    SESSIONS[session.id] = session
    return session


def get_session(game_id: str) -> GameSession | None:
    """In-memory lookup only. Prefer thulla.persist.get_or_load_session for API."""
    return SESSIONS.get(game_id)
