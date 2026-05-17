#!/usr/bin/env bash
# Verify chess prerequisites before building chess mode.
echo '--- stockfish binary ---'
which stockfish 2>/dev/null || echo 'NOT INSTALLED'
echo '--- python-chess ---'
cd /home/rpclaw/frankie
~/.local/bin/uv run python -c 'import chess; print(f"python-chess {chess.__version__}")' 2>&1 || echo 'python-chess NOT installed'
echo '--- chess.engine async ---'
~/.local/bin/uv run python -c 'import chess.engine; print("chess.engine importable")' 2>&1 || echo 'chess.engine NOT importable'
