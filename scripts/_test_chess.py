"""Smoke test for chess mode: square mapping + JSON parse + Stockfish."""

from __future__ import annotations

import asyncio

import chess
import chess.engine

from frankie.modes.chess import (
    load_chess_config,
    parse_board_state,
    square_to_world,
)


async def main() -> int:
    cfg = load_chess_config()
    print(f"a1 -> {square_to_world('a1', cfg)}")
    print(f"h1 -> {square_to_world('h1', cfg)}")
    print(f"a8 -> {square_to_world('a8', cfg)}")
    print(f"h8 -> {square_to_world('h8', cfg)}")
    print(f"e4 -> {square_to_world('e4', cfg)}")

    # Parse a fake board state.
    fake_json = '{"a1": "R", "e1": "K", "h1": "R", "a8": "r", "e8": "k", "h8": "r"}'
    board = parse_board_state(fake_json, whose_turn=chess.BLACK)
    print(f"parsed board (black to move): {board.fen()}")
    assert board.is_valid()

    # Markdown-fenced JSON.
    fenced = '```json\n{"e2": "P", "e7": "p"}\n```'
    board2 = parse_board_state(fenced, whose_turn=chess.WHITE)
    print(f"parsed fenced: {board2.fen()}")

    # Stockfish.
    transport, engine = await chess.engine.popen_uci(cfg.stockfish_path)
    try:
        start_board = chess.Board()
        result = await engine.play(start_board, chess.engine.Limit(time=0.5))
        print(f"stockfish first move: {start_board.san(result.move)}")
    finally:
        await engine.quit()

    print("chess smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
