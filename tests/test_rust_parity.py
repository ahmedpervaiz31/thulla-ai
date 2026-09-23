"""Parity: Rust engine+encode vs Python ThullaEnv on identical deals/actions."""

from __future__ import annotations

import unittest

import numpy as np

from thulla.cards import Card, parse_card
from thulla.game import ThullaGame
from thulla_dmc.encode import ASK, PASS, card_index
from thulla_dmc.env import DummySeat, ThullaEnv
from thulla_dmc.rust_env import RustThullaEnv, rust_available


def C(number, colour):
    return Card(number, colour)


def _action_key(a):
    if a == ASK:
        return (1, 52)
    if a == PASS:
        return (1, 53)
    return (0, card_index(a))


def _sorted_legal(legal):
    return sorted(legal, key=_action_key)


def _python_env_from_hands(hands, ace_holder: int) -> ThullaEnv:
    """Mirror Rust reset_hands using the Python ThullaEnv/Game."""
    env = ThullaEnv()
    players = [DummySeat(f"P{i}") for i in range(4)]
    env.game = ThullaGame(players, verbose=False)
    env.game.set_hands(hands, ace_spades_holder_idx=ace_holder)
    env.play_history = []
    env.phase = "play"
    env._take_queue = []
    env._take_pos = 0
    env._take_leader = None
    env.leader = ace_holder
    env.trick = env.game.begin_trick(ace_holder, first_trick=True)
    assert env.trick is not None
    return env


@unittest.skipUnless(rust_available(), "thulla_rust not installed")
class RustPythonParityTests(unittest.TestCase):
    def test_first_trick_obs_and_forced_as(self):
        hands = [
            [C("A", "Spade"), C("2", "Heart"), C("3", "Club")],
            [C("2", "Spade"), C("4", "Heart"), C("5", "Club")],
            [C("3", "Spade"), C("6", "Heart"), C("7", "Club")],
            [C("4", "Spade"), C("8", "Heart"), C("9", "Club")],
        ]
        ace = 0
        py = _python_env_from_hands(hands, ace)
        rs = RustThullaEnv()
        robs = rs.reset_hands(hands, ace)
        pobs = py._obs_for_current()

        self.assertEqual(pobs["position"], robs["position"])
        self.assertEqual(pobs["phase"], robs["phase"])
        self.assertEqual(
            [_action_key(a) for a in _sorted_legal(pobs["legal_actions"])],
            [_action_key(a) for a in _sorted_legal(robs["legal_actions"])],
        )
        np.testing.assert_allclose(pobs["x_no_action"], robs["x_no_action"], atol=1e-6)
        np.testing.assert_allclose(pobs["z"], robs["z"], atol=1e-6)

    def test_full_game_greedy_lowest_legal(self):
        """Same fixed deal; always play lowest legal by card index / ASK before PASS."""
        hands = [
            [
                C("A", "Spade"),
                C("5", "Spade"),
                C("2", "Heart"),
                C("9", "Club"),
                C("J", "Diamond"),
            ],
            [
                C("K", "Spade"),
                C("3", "Heart"),
                C("4", "Club"),
                C("6", "Diamond"),
                C("8", "Heart"),
            ],
            [
                C("Q", "Spade"),
                C("7", "Heart"),
                C("10", "Club"),
                C("2", "Diamond"),
                C("3", "Club"),
            ],
            [
                C("J", "Spade"),
                C("4", "Heart"),
                C("5", "Club"),
                C("7", "Diamond"),
                C("9", "Heart"),
            ],
        ]
        ace = 0
        py = _python_env_from_hands([list(h) for h in hands], ace)
        rs = RustThullaEnv()
        robs = rs.reset_hands([list(h) for h in hands], ace)
        pobs = py._obs_for_current()

        steps = 0
        while True:
            self.assertEqual(pobs["position"], robs["position"], f"step {steps} seat")
            self.assertEqual(pobs["phase"], robs["phase"], f"step {steps} phase")
            pl = _sorted_legal(pobs["legal_actions"])
            rl = _sorted_legal(robs["legal_actions"])
            self.assertEqual(
                [_action_key(a) for a in pl],
                [_action_key(a) for a in rl],
                f"step {steps} legal",
            )
            np.testing.assert_allclose(
                pobs["x_no_action"], robs["x_no_action"], atol=1e-5, err_msg=f"x step {steps}"
            )
            np.testing.assert_allclose(pobs["z"], robs["z"], atol=1e-5, err_msg=f"z step {steps}")

            action = pl[0]
            pobs, prew, pdone, _ = py.step(action)
            robs, rrew, rdone, _ = rs.step(action)
            steps += 1
            self.assertEqual(pdone, rdone, f"done step {steps}")
            if pdone:
                np.testing.assert_allclose(prew, rrew, atol=1e-5)
                break
            self.assertIsNotNone(pobs)
            self.assertIsNotNone(robs)
            if steps > 500:
                self.fail("game too long")

        self.assertGreater(steps, 5)

    def test_rust_env_runs_random_seed(self):
        env = RustThullaEnv()
        obs = env.reset(seed=12345)
        self.assertIn("x_batch", obs)
        self.assertEqual(obs["x_no_action"].shape[0], 439)
        # play a few steps
        for _ in range(3):
            legal = env.legal_actions()
            obs, rewards, done, _ = env.step(legal[0])
            if done:
                break


class RustAvailabilityTests(unittest.TestCase):
    def test_import_path(self):
        # Soft check: documents whether acceleration is live.
        print("rust_available=", rust_available())


if __name__ == "__main__":
    unittest.main()
