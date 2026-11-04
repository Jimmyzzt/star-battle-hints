"""Command line interface. Coordinates in user JSON and CLI output are 1-based."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .model import Puzzle
from .solver import StarBattleSolver
from .logic import diagnose, next_hint
from .ladder import hint_ladder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Star Battle: exact checking and spoiler-controlled hints')
    parser.add_argument('board', type=Path, help='JSON puzzle file')
    parser.add_argument('mode', nargs='?', choices=['hint','check','solve','ladder'], default='hint')
    parser.add_argument('--level', type=int, choices=[1,2,3], default=2,
                        help='1 direction only; 2 one local step; 3 global proof')
    parser.add_argument('--max-probes', type=int, default=60)
    parser.add_argument('--steps', type=int, default=3, help='number of precomputed hint steps for ladder (1..15)')
    parser.add_argument('--time-limit', type=float, default=15.,
                        help='seconds per exact feasibility call')
    parser.add_argument('--reveal', action='store_true',
                        help='required for showing the full solution')
    args = parser.parse_args(argv)
    try:
        puzzle = Puzzle.from_dict(json.loads(args.board.read_text(encoding='utf-8')))
        solver = StarBattleSolver(puzzle, time_limit=args.time_limit)
        warnings = [f'{region} 似乎不连通，请核对粗黑区域线'
                    for region in puzzle.disconnected_regions()]
        if args.mode == 'hint':
            payload = next_hint(puzzle, solver, level=args.level,
                                max_probes=args.max_probes)
        elif args.mode == 'check':
            payload = diagnose(puzzle, solver, max_probes=args.max_probes)
        elif args.mode == 'ladder':
            payload = hint_ladder(puzzle, solver, steps=args.steps)
        else:
            if not args.reveal:
                parser.error('the solve mode requires --reveal to prevent spoilers')
            result = solver.with_marks()
            payload = {'status':result.status,
                       'solution':([[r+1,c+1] for r,c in sorted(result.solution)]
                                   if result.solution is not None else None),
                       'reason':result.reason}
            if result.status == 'sat':
                payload['uniqueness'] = solver.uniqueness(result.solution)
        payload['warnings'] = warnings
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get('status') not in ('unknown', 'unsat') and payload.get('type') != 'unknown' else 2
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({'error':str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
