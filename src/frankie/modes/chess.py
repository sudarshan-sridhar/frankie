"""Chess mode.

Detects the board state with Claude Vision (returning a JSON object that
maps square names to piece symbols), feeds it to python-chess, asks
Stockfish for the next move, and executes the move with the arm. Board
square -> world XY comes from data/calibration/chess.json which the user
calibrates to their physical board.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import chess
import chess.engine
import structlog
from pydantic import BaseModel, Field

from frankie.config import get_settings
from frankie.modes.base import ModeResponse

if TYPE_CHECKING:
    from frankie.hardware.arm import Arm
    from frankie.hardware.kinematics import Kinematics
    from frankie.vision.camera import Camera
    from frankie.reasoning.router import ReasoningRouter

log = structlog.get_logger(__name__)

# Prompt is tightly worded so the response can be json.loads'd directly.
BOARD_PROMPT = (
    "This is a top-down view of a chess board. For each occupied square, "
    "report its piece using SAN symbols: uppercase = white (P, N, B, R, Q, K), "
    "lowercase = black (p, n, b, r, q, k). Omit empty squares. "
    "Reply with ONLY a JSON object mapping square names to piece symbols. "
    "Example: {\"a1\": \"R\", \"e1\": \"K\", \"e8\": \"k\"}. "
    "No prose, no markdown fences."
)

# Recognise "your turn" / "play" / "go" as the trigger to make a move.
PLAY_RE = re.compile(r"\b(your\s+turn|play|move|go|continue)\b", re.IGNORECASE)
RESET_RE = re.compile(r"\b(reset|restart|new\s+game)\b", re.IGNORECASE)


class ChessConfig(BaseModel):
    """Schema for data/calibration/chess.json."""

    version: int = 1
    a1_world_xy_mm: tuple[float, float]
    square_mm: float = 22.0
    files_axis_world: tuple[float, float] = Field(default=(0.0, 1.0))
    ranks_axis_world: tuple[float, float] = Field(default=(1.0, 0.0))
    piece_pick_z_mm: float = 15.0
    piece_place_z_mm: float = 20.0
    captured_world_xy_mm: tuple[float, float] = Field(default=(60.0, -120.0))
    stockfish_path: str = "/usr/games/stockfish"
    stockfish_time_s: float = 1.0


def _default_chess_path() -> Path:
    return get_settings().calibration_dir / "chess.json"


def load_chess_config(path: Path | None = None) -> ChessConfig:
    target = path or _default_chess_path()
    return ChessConfig.model_validate_json(target.read_text(encoding="utf-8"))


def square_to_world(square_name: str, cfg: ChessConfig) -> tuple[float, float]:
    """Map a SAN square name (e.g. 'e4') to world XY mm via the chess.json mapping."""
    sq = chess.parse_square(square_name)
    file = chess.square_file(sq)
    rank = chess.square_rank(sq)
    fx, fy = cfg.files_axis_world
    rx, ry = cfg.ranks_axis_world
    x = cfg.a1_world_xy_mm[0] + file * cfg.square_mm * fx + rank * cfg.square_mm * rx
    y = cfg.a1_world_xy_mm[1] + file * cfg.square_mm * fy + rank * cfg.square_mm * ry
    return (x, y)


def _strip_code_fence(text: str) -> str:
    """Claude sometimes wraps JSON in ```json ... ```; strip that if present."""
    text = text.strip()
    if text.startswith("```"):
        # drop the first ``` line and the closing fence if present
        lines = text.splitlines()
        lines = lines[1:-1] if lines and lines[-1].startswith("```") else lines[1:]
        text = "\n".join(lines).strip()
    return text


def parse_board_state(text: str, whose_turn: chess.Color) -> chess.Board:
    """Parse the Claude Vision JSON response into a python-chess Board."""
    stripped = _strip_code_fence(text)
    data = json.loads(stripped)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object, got {type(data).__name__}")
    board = chess.Board.empty()
    for square_name, symbol in data.items():
        if not isinstance(square_name, str) or not isinstance(symbol, str):
            raise ValueError(f"invalid entry: {square_name!r} -> {symbol!r}")
        sq = chess.parse_square(square_name.strip().lower())
        piece = chess.Piece.from_symbol(symbol.strip())
        board.set_piece_at(sq, piece)
    board.turn = whose_turn
    return board


class ChessMode:
    """Vision-driven chess engine pilot."""

    name = "chess"

    def __init__(
        self,
        arm: Arm,
        kinematics: Kinematics,
        camera: Camera,
        router: ReasoningRouter,
        cfg: ChessConfig | None = None,
    ) -> None:
        self._arm = arm
        self._ik = kinematics
        self._camera = camera
        self._router = router
        self._cfg = cfg or load_chess_config()
        self._engine: chess.engine.UciProtocol | None = None
        self._engine_transport: asyncio.SubprocessTransport | None = None
        self._board: chess.Board = chess.Board()
        # The arm always plays the side whose turn it is when "your turn"
        # arrives; default to black so a fresh game lets the human open as
        # white. Update by reading the parsed board state.
        self._arm_color: chess.Color = chess.BLACK
        self._active = False

    async def start(self) -> None:
        try:
            transport, engine = await chess.engine.popen_uci(self._cfg.stockfish_path)
            self._engine_transport = transport
            self._engine = engine
        except Exception:
            log.exception("chess.engine_open_failed", path=self._cfg.stockfish_path)
            self._engine = None
        self._board = chess.Board()
        self._active = True
        log.info("chess.start", engine_ok=self._engine is not None)

    async def stop(self) -> None:
        self._active = False
        if self._engine is not None:
            try:
                await self._engine.quit()
            except Exception:
                log.exception("chess.engine_quit_failed")
            self._engine = None
            self._engine_transport = None
        log.info("chess.stop")

    async def handle_command(
        self, command: str, context: dict[str, Any]
    ) -> ModeResponse:
        del context
        if not self._active:
            return ModeResponse(
                spoken="Chess mode is not running.",
                action_taken="rejected",
                next_state={"reason": "inactive"},
            )
        if RESET_RE.search(command):
            self._board = chess.Board()
            return ModeResponse(
                spoken="Reset. New game ready.",
                action_taken="reset",
                next_state={"fen": self._board.fen()},
            )
        if not PLAY_RE.search(command):
            return ModeResponse(
                spoken="Say 'your turn' to make me play, or 'new game' to reset.",
                action_taken="help",
                next_state={"fen": self._board.fen()},
            )
        if self._engine is None:
            return ModeResponse(
                spoken="The chess engine isn't running. Restart the mode.",
                action_taken="no_engine",
                next_state={},
            )

        try:
            frame = await self._camera.snapshot()
        except TimeoutError:
            return ModeResponse(
                spoken="I can't see the camera right now.",
                action_taken="camera_timeout",
                next_state={},
            )

        raw_result = await self._router.describe_image(frame, BOARD_PROMPT)
        raw = raw_result.text
        try:
            board = parse_board_state(raw, whose_turn=self._arm_color)
        except (ValueError, json.JSONDecodeError) as exc:
            log.warning("chess.parse_failed", raw=raw[:200], err=str(exc))
            return ModeResponse(
                spoken="I couldn't read the board cleanly. Try again.",
                action_taken="parse_failed",
                next_state={"raw": raw[:200]},
            )
        if not board.is_valid():
            return ModeResponse(
                spoken="The board state I see isn't legal. Adjust the pieces.",
                action_taken="invalid_board",
                next_state={"fen": board.fen()},
            )
        self._board = board

        try:
            result = await self._engine.play(
                board,
                chess.engine.Limit(time=self._cfg.stockfish_time_s),
            )
        except Exception as exc:
            log.exception("chess.engine_play_failed")
            return ModeResponse(
                spoken="The engine failed to pick a move.",
                action_taken="engine_failed",
                next_state={"error": str(exc)},
            )
        move = result.move
        if move is None:
            return ModeResponse(
                spoken="No legal move available. Check the position.",
                action_taken="no_move",
                next_state={"fen": board.fen()},
            )
        san = board.san(move)

        src_name = chess.square_name(move.from_square)
        dst_name = chess.square_name(move.to_square)
        src_xy = square_to_world(src_name, self._cfg)
        dst_xy = square_to_world(dst_name, self._cfg)

        # If the destination has a piece, the move is a capture. Pull the
        # captured piece off the board to the basket position first.
        if board.is_capture(move):
            await self._arm.pick_at(
                dst_xy,
                self._ik,
                pick_z_mm=self._cfg.piece_pick_z_mm,
            )
            await self._arm.place_at(
                self._cfg.captured_world_xy_mm,
                self._ik,
                place_z_mm=self._cfg.piece_place_z_mm,
            )

        await self._arm.pick_at(
            src_xy,
            self._ik,
            pick_z_mm=self._cfg.piece_pick_z_mm,
        )
        await self._arm.place_at(
            dst_xy,
            self._ik,
            place_z_mm=self._cfg.piece_place_z_mm,
        )

        board.push(move)
        self._board = board
        # Arm's colour persists across turns; the human plays the other side.
        log.info("chess.move", san=san, src=src_name, dst=dst_name)
        return ModeResponse(
            spoken=f"I played {san}.",
            action_taken=f"played:{san}",
            next_state={
                "san": san,
                "fen": board.fen(),
                "src": src_name,
                "dst": dst_name,
                "src_world_xy": list(src_xy),
                "dst_world_xy": list(dst_xy),
            },
        )


__all__ = [
    "BOARD_PROMPT",
    "ChessConfig",
    "ChessMode",
    "load_chess_config",
    "parse_board_state",
    "square_to_world",
]
