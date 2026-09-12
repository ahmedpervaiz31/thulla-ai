import argparse

from thulla.game import ThullaGame
from thulla.players import HumanPlayer, ComputerPlayer


def parse_player_count(argv=None):
    parser = argparse.ArgumentParser(description="Play Thulla (Getaway)")
    parser.add_argument(
        "-p",
        "--players",
        type=int,
        default=None,
        help="Number of players (3-8). Default 4, or prompted if omitted.",
    )
    args = parser.parse_args(argv)
    n = args.players
    if n is None:
        raw = input("Number of players (3-8) [4]: ").strip()
        n = int(raw) if raw else 4
    if n < 3 or n > 8:
        raise SystemExit("Player count must be between 3 and 8.")
    return n


def build_players(player_cnt):
    players = [HumanPlayer("Player 0 (You)")]
    for i in range(1, player_cnt):
        players.append(ComputerPlayer(f"Player {i} (CPU)"))
    return players


def main(argv=None):
    player_cnt = parse_player_count(argv)
    game = ThullaGame(build_players(player_cnt))
    game.shuffle_and_deal()
    game.game_loop()
    game.print_winners()


if __name__ == "__main__":
    main()
