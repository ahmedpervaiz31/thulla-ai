"""Trick start, play, CPU play, and reveal / completion bookkeeping."""

from __future__ import annotations

from typing import Any

from ..cards import parse_card, valid_moves
from ..players import ComputerPlayer, choose_computer_card
from .seats import InteractiveSeat


class TrickMixin:
    """Methods mixed into GameSession for the trick / reveal phases."""

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

    def _play_cpu_card(self, seat: int) -> str:
        assert self.trick is not None
        player = self.game.players[seat]
        if isinstance(player, InteractiveSeat):
            raise RuntimeError("cannot auto-play interactive seat")
        expected = self.game.expected_for_seat(self.trick, seat)
        view = self.game.view_for_seat(self.trick, seat)
        hand_before = [c.code() for c in player.hand]
        legal = [c.code() for c in valid_moves(player.hand, expected)]
        # Same Ideal Move reasoning as humans — logged for bot-policy tuning.
        advice = self._snapshot_advice_for_pending()
        if isinstance(player, ComputerPlayer):
            moves = valid_moves(player.hand, expected)
            card = choose_computer_card(
                player.hand, moves, expected, view, samples=player.mc_samples
            )
        else:
            # ScriptedPlayer / RandomPlayer: play_turn may already remove the card
            card = player.play_turn(expected, view)
        self._log_play(
            seat, card, hand_before=hand_before, legal=legal, advice=advice
        )
        return self.game.apply_play(self.trick, seat, card)

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
