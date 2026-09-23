"""Client DTO projection used by the web UI."""

from __future__ import annotations


class SerializeMixin:
    """Methods mixed into GameSession for web state serialization."""

    def to_dict(self, *, reveal_hands: bool = False) -> dict:
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
            if reveal_hands:
                entry["hand"] = [c.code() for c in p.hand]
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
        elif (
            self.phase == "trick_reveal"
            and self.trick is not None
            and self.trick.result == "thulla"
            and self.trick.thulla_by is not None
        ):
            # Keep the thulla-giver highlighted while the pot is held.
            whose_turn = self.trick.thulla_by

        # Lazy import: persist imports GameSession.
        from ..persist import info_to_dict

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
            "bot_kind": getattr(self, "bot_kind", "heuristic"),
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
