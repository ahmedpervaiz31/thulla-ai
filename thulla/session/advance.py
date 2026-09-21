"""Step / auto-advance until human input (or equivalent)."""

from __future__ import annotations


class AdvanceMixin:
    """Methods mixed into GameSession for paced CPU / reveal advancement."""

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
            advice = self._snapshot_advice_for_pending()
            accept = self._decide_cpu_take(seat)
            self._resolve_take_ask(
                seat,
                accept,
                advice=advice,
                human_decision="ask" if accept else "decline_ask",
            )
        elif self.pending["type"] == "give":
            advice = self._snapshot_advice_for_pending()
            accept = self._decide_cpu_give(seat)
            self._resolve_give(
                seat,
                accept,
                advice=advice,
                human_decision="give" if accept else "refuse",
            )
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
