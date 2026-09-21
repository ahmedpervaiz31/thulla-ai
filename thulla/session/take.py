"""Take-phase queue, ask/give resolution, and heads-up skip."""

from __future__ import annotations

from typing import Any


class TakeMixin:
    """Methods mixed into GameSession for the take / give phases."""

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

        # CPU / scripted victim always gives (exiting = not last).
        self._complete_take(
            seat,
            target,
            True,
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
