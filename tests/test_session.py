import unittest

from thulla.cards import Card
from thulla.players import ScriptedPlayer
from thulla.session import GameSession, InteractiveSeat


def C(number, colour):
    return Card(number, colour)


class SessionHumanPlayTests(unittest.TestCase):
    def test_human_pending_as_then_play_advances(self):
        session = GameSession("human", 4, deal=False)
        # Replace CPUs with scripted seats for a controlled first trick.
        session.game.players[1] = ScriptedPlayer("CPU1")
        session.game.players[2] = ScriptedPlayer("CPU2")
        session.game.players[3] = ScriptedPlayer("CPU3")
        session.game.players[1].queue_plays([C("2", "Spade")])
        session.game.players[2].queue_plays([C("3", "Spade")])
        session.game.players[3].queue_plays([C("4", "Spade")])

        session.game.set_hands(
            [
                [C("A", "Spade"), C("9", "Club")],
                [C("2", "Spade"), C("8", "Club")],
                [C("3", "Spade"), C("7", "Club")],
                [C("4", "Spade"), C("6", "Club")],
            ],
            ace_spades_holder_idx=0,
        )
        session.leader = 0
        session._start_trick(first_trick=True)
        session.advance_until_input()

        self.assertEqual(session.pending["type"], "play")
        self.assertEqual(session.pending["seat"], 0)
        self.assertIn("AS", session.pending["legal"])
        self.assertIsInstance(session.game.players[0], InteractiveSeat)

        state = session.play_card("AS")
        # Paced play: human card only — next seat still to act (or reveal if solo).
        self.assertNotIn("AS", state["your_hand"])
        self.assertIsNotNone(state["pending"])
        self.assertIn(state["pending"]["type"], ("play", "reveal"))
        if state["pending"]["type"] == "play":
            self.assertEqual(state["pending"]["seat"], 1)
            self.assertEqual(len(state["trick"]["cards"]), 1)

        # Finish trick via steps; final play should land on reveal with full pot visible.
        while state["pending"] and state["pending"]["type"] == "play":
            state = session.step()
        self.assertEqual(state["pending"]["type"], "reveal")
        self.assertEqual(len(state["trick"]["cards"]), 4)
        state = session.step()
        self.assertEqual(state["phase"], "take")


class SessionTakePromptTests(unittest.TestCase):
    def test_human_take_prompt_then_decline(self):
        session = GameSession("human", 3, deal=False)
        session.game.players[1] = ScriptedPlayer("CPU1")
        session.game.players[2] = ScriptedPlayer("CPU2")

        # Skip first trick machinery: jump into take phase with human as leader.
        session.game.set_hands(
            [
                [C("A", "Heart"), C("K", "Heart")],
                [C("2", "Club")],
                [C("3", "Diamond"), C("4", "Diamond")],
            ]
        )
        session.leader = 0
        session.phase = "take"
        session.take_leader = 0
        session.take_queue = [0, 1, 2]
        session._set_take_pending_or_advance()

        self.assertEqual(session.pending["type"], "take")
        self.assertEqual(session.pending["seat"], 0)
        self.assertEqual(session.pending["target"], 1)
        self.assertEqual(session.pending["n_cards"], 1)

        state = session.answer_take(False)
        self.assertIsNotNone(state)
        # No bulk advance: next take offer is the following seat.
        self.assertEqual(state["pending"]["type"], "take")
        self.assertEqual(state["pending"]["seat"], 1)


class SessionGivePromptTests(unittest.TestCase):
    def test_human_can_refuse_when_asked(self):
        session = GameSession("human", 3, deal=False)
        session.game.players[1] = ScriptedPlayer("CPU1", take_decisions=[True])
        session.game.players[2] = ScriptedPlayer("CPU2")
        session.game.set_hands(
            [
                [C("A", "Heart"), C("K", "Heart")],
                [C("2", "Club")],
                [C("3", "Diamond"), C("4", "Diamond")],
            ]
        )
        # CPU1 asks human (seat 0 is next after 1? Order from leader 1: 1,2,0)
        # Set leader to 1 so first asker is CPU1 targeting next=2, then 2 targeting 0...
        # Simpler: leader 2, queue starts at 2 -> asks 0 (human).
        session.leader = 2
        session.phase = "take"
        session.take_leader = 2
        session.take_queue = [2]
        # Force pending give: CPU asker already said yes
        session._set_give_pending(2, 0, 2)
        self.assertEqual(session.pending["type"], "give")
        self.assertEqual(session.pending["seat"], 0)

        state = session.answer_give(False)
        self.assertEqual(len(session.game.players[0].hand), 2)
        self.assertIn(0, session.game.active_player_indices)
        self.assertIn("refuse", (state.get("last_event") or "").lower())


class SessionFinishTests(unittest.TestCase):
    def test_finish_when_one_left(self):
        session = GameSession("human", 3, deal=False)
        session.game.set_hands(
            [
                [C("A", "Heart")],
                [],
                [],
            ]
        )
        # Manually mark two got away
        session.game.active_player_indices = [0]
        session.game.winners = [session.game.players[1], session.game.players[2]]
        session._finish_game()
        data = session.to_dict()
        self.assertTrue(data["finished"])
        self.assertEqual(data["loser"], "You")
        self.assertEqual(len(data["winners"]), 2)
        self.assertIn("public_info", data)
        self.assertIn("discarded", data["public_info"])
        self.assertIn("voids", data["public_info"])
        self.assertIn("known_holdings", data["public_info"])


class SessionHeadsUpTests(unittest.TestCase):
    def test_skips_take_phase_when_two_left(self):
        session = GameSession("human", 3, deal=False)
        session.game.players[1] = ScriptedPlayer("CPU1")
        session.game.players[2] = ScriptedPlayer("CPU2")
        session.game.set_hands(
            [
                [C("A", "Heart"), C("K", "Heart")],
                [C("2", "Club"), C("3", "Club")],
                [],
            ]
        )
        session.game.active_player_indices = [0, 1]
        session.game.winners = [session.game.players[2]]
        session.game.info.active_indices = [0, 1]
        session.game.info.sync_hands(session.game.players)
        session.leader = 0
        session._begin_take_pass()
        self.assertNotEqual(session.phase, "take")
        self.assertIn(session.phase, ("trick", "first_trick"))
        self.assertEqual(session.pending["type"], "play")

    def test_client_public_info_shows_deduced_opponent(self):
        from thulla.cards import create_deck

        session = GameSession("human", 3, deal=False)
        me = [C("2", "Heart"), C("3", "Club")]
        opp = [C("4", "Spade"), C("5", "Diamond")]
        rest = [c for c in create_deck() if c not in me and c not in opp]
        session.game.set_hands([me, opp, []])
        session.game.active_player_indices = [0, 1]
        session.game.winners = [session.game.players[2]]
        session.game.info.active_indices = [0, 1]
        session.game.info.discarded = set(rest)
        session.game.info.sync_hands(session.game.players)
        data = session.to_dict()
        self.assertTrue(data["public_info"].get("complete_info"))
        known = set(data["public_info"]["known_holdings"]["1"])
        self.assertEqual(known, {"4S", "5D"})


class SessionThullaHighlightTests(unittest.TestCase):
    def test_thulla_giver_highlighted_during_reveal(self):
        session = GameSession("human", 3, deal=False)
        session.game.players[1] = ScriptedPlayer("CPU1")
        session.game.players[2] = ScriptedPlayer("CPU2")
        session.game.players[1].queue_plays([C("9", "Heart")])
        session.game.players[2].queue_plays([C("K", "Spade")])

        session.game.set_hands(
            [
                [C("2", "Heart"), C("4", "Club")],
                [C("9", "Heart"), C("5", "Club")],
                [C("K", "Spade"), C("6", "Club")],
            ]
        )
        session.leader = 0
        session._start_trick(first_trick=False)
        session.advance_until_input()

        state = session.play_card("2H")
        while state.get("pending") and state["pending"]["type"] == "play":
            state = session.step()

        self.assertEqual(state["phase"], "trick_reveal")
        self.assertEqual(state["pending"]["type"], "reveal")
        self.assertIn("THULLA", state["last_event"] or "")
        # CPU2 dumped off-suit — keep their seat lit while pot is held.
        self.assertEqual(state["whose_turn"], 2)
        self.assertEqual(session.trick.thulla_by, 2)


class SessionAiModeTests(unittest.TestCase):
    def test_ai_mode_step_plays_without_human(self):
        session = GameSession("ai", 3)
        self.assertIsNone(session.human_seat)
        self.assertEqual(session.pending["type"], "play")
        before = session.pending["seat"]
        session.step()
        # Either next seat in same trick, or phase changed
        if session.pending and session.pending["type"] == "play":
            self.assertNotEqual(
                (session.pending["seat"], len(session.trick.plays) if session.trick else 0),
                (before, 0),
            )
        self.assertIn(session.phase, ("first_trick", "take", "trick", "finished"))


if __name__ == "__main__":
    unittest.main()
