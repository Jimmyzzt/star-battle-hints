"""Human-oriented, conservative hints; exact checks for mistakes."""
from __future__ import annotations

from itertools import combinations
from typing import Any
from .model import Cell, Puzzle, fmt
from .solver import StarBattleSolver


def _reported(kind: str, cell: Cell | None = None, *, level: int,
              scope: str = '', why: str = '') -> dict[str, Any]:
    return {'type': kind, 'cell': [cell[0]+1,cell[1]+1] if cell else None,
            'level': level, 'scope': scope, 'reason': why}


def _safe_cells(puzzle: Puzzle) -> set[Cell]:
    occupied = set(puzzle.stars)
    banned = set(puzzle.crosses)
    for cell in occupied:
        banned.update(puzzle.nearby(cell))
    return {(r,c) for r in range(puzzle.size) for c in range(puzzle.size)
            if (r,c) not in banned and (r,c) not in occupied}


def _local_hint(puzzle: Puzzle, max_patterns: int = 250_000) -> dict[str, Any] | None:
    """Patterns are a relaxation of global constraints: any deduction is sound."""
    possible = _safe_cells(puzzle)
    k = puzzle.stars_per_unit
    for name, cells in puzzle.unit_groups():
        marks = sorted(set(cells) & set(puzzle.stars))
        open_cells = sorted(set(cells) & possible)
        if len(marks) == k and open_cells:
            return _reported('cross', open_cells[0], level=1, scope=name,
                             why=f'{name} 已有 {k} 颗星，其他格子不能再放星。')
        if len(marks) + len(open_cells) == k and open_cells:
            return _reported('star', open_cells[0], level=1, scope=name,
                             why=f'{name} 还差 {len(open_cells)} 颗星，剩余可选格刚好这么多。')
    for star in sorted(puzzle.stars):
        for cell in sorted(puzzle.nearby(star)):
            if cell not in puzzle.stars and cell not in puzzle.crosses:
                return _reported('cross', cell, level=1,
                                 scope=f'{fmt(star)} 的邻域',
                                 why=f'{fmt(star)} 已放星；星星不能接触，含斜角。')

    for name, cells in puzzle.unit_groups():
        fixed = set(cells) & set(puzzle.stars)
        available = sorted(set(cells) & possible)
        needed = k-len(fixed)
        if not (1 <= needed <= len(available)):
            continue
        pattern_count = 0
        union: set[Cell] = set()
        intersection: set[Cell] | None = None
        complete = True
        for chosen in combinations(available, needed):
            # Only candidates within the same unit must be mutually non-touching.
            if any(abs(a[0]-b[0]) <= 1 and abs(a[1]-b[1]) <= 1
                   for a,b in combinations(chosen,2)):
                continue
            pattern_count += 1
            if pattern_count > max_patterns:
                complete = False
                break
            chosen_set = set(chosen)
            union.update(chosen_set)
            intersection = chosen_set if intersection is None else intersection & chosen_set
        if complete and pattern_count:
            if intersection:
                cell = min(intersection)
                return _reported('star', cell, level=2, scope=name,
                    why=f'只考虑{name}的 {k} 星与不相邻规则，共有 {pattern_count} 种局部合法摆法；'
                        f'{fmt(cell)} 出现在每一种摆法中。')
            not_used = set(available)-union
            if not_used:
                cell = min(not_used)
                return _reported('cross', cell, level=2, scope=name,
                    why=f'只考虑{name}共有 {pattern_count} 种局部合法摆法；'
                        f'{fmt(cell)} 无法出现在任何摆法中。')
    return None


def next_hint(puzzle: Puzzle, solver: StarBattleSolver, *,
              level: int = 2, max_probes: int = 60) -> dict[str, Any]:
    """One step; never reveal the complete solution unless explicitly requested."""
    current = solver.with_marks()
    if current.status == 'unsat':
        return {'type':'contradiction', 'level':0,
                'reason':'当前星星与红叉彼此矛盾；请先运行 check 排错。'}
    if current.status == 'unknown':
        return {'type':'unknown', 'level':0,
                'reason':'求解超时/未知；不能把超时当成无解。'}
    if level >= 1:
        result = _local_hint(puzzle)
        if result is not None:
            if level == 1:
                # Direction-only: hide the actual cell even if found.
                result['cell'] = None
                result['reason'] = f'先观察{result["scope"]}，检查星数与不相邻规则。'
            return result
    if level < 3:
        return {'type':'deeper', 'level':2,
                'reason':'暂未找到局部一步提示；可使用 --level 3 进行全局反证。'}

    # Look for a forced star first. All exact queries preserve *all* user marks.
    possible = _safe_cells(puzzle)
    remaining = sorted(current.solution - puzzle.stars)
    attempts = 0
    for cell in remaining:
        if attempts >= max_probes: break
        attempts += 1
        test = solver.solve(stars=puzzle.stars, crosses=puzzle.crosses | {cell})
        if test.status == 'unsat':
            return _reported('star', cell, level=3, scope='全局反证',
                    why=f'假设 {fmt(cell)} 不是星星，整盘约束无解；所以此格必为星。'
                        '这是计算机验证的全局结论，不等于已经找到简短的人工证明。')
        if test.status == 'unknown':
            return {'type':'unknown','reason':'反证验证超时，不能确定结论。'}
    for cell in sorted(possible-current.solution):
        if attempts >= max_probes: break
        attempts += 1
        test = solver.solve(stars=puzzle.stars | {cell}, crosses=puzzle.crosses)
        if test.status == 'unsat':
            return _reported('cross', cell, level=3, scope='全局反证',
                    why=f'假设 {fmt(cell)} 是星星，整盘约束无解；所以此格不可放星。')
        if test.status == 'unknown':
            return {'type':'unknown','reason':'反证验证超时，不能确定结论。'}
    return {'type':'deeper', 'level':3,
            'reason':f'在 {attempts} 次全局尝试内未发现可证明的一格；'
                     '不是说不存在逻辑提示，可增加 --max-probes。'}


def diagnose(puzzle: Puzzle, solver: StarBattleSolver,
             *, max_probes: int = 200) -> dict[str, Any]:
    """Never infer 'wrong' solely by comparing with one arbitrary solution."""
    base = solver.solve()
    if base.status != 'sat':
        return {'status':base.status, 'reason': '空盘无解或求解未完成：请核对区域转录。'}
    another = solver.solve(exclude_solution=base.solution)
    unique = another.status == 'unsat'
    current = solver.with_marks()
    out: dict[str, Any] = {
        'status':current.status,
        'puzzle_uniqueness': 'unique' if unique else ('multiple' if another.status=='sat' else 'unknown'),
        'invalid_stars':[], 'invalid_crosses':[], 'uncertain':[]}
    if unique:
        out['invalid_stars'] = [[r+1,c+1] for r,c in sorted(puzzle.stars-base.solution)]
        out['invalid_crosses'] = [[r+1,c+1] for r,c in sorted(puzzle.crosses & base.solution)]
        out['reason'] = ('唯一解已证明：列出所有与唯一解冲突的用户标记。'
                         '无法从最终截图判断哪一个标记最早填错。')
        return out
    if current.status == 'sat':
        out['reason'] = '原题存在多个解，当前标记仍可扩展为一个完整解；不能判错。'
        return out
    if current.status == 'unknown':
        out['reason'] = '当前标记可满足性未知，不能判断对错。'
        return out
    # For non-unique puzzle, prove only individually impossible marks.
    checked = 0
    for cell in sorted(puzzle.stars):
        if checked >= max_probes: break
        checked += 1
        res = solver.solve(stars={cell})
        if res.status == 'unsat':
            out['invalid_stars'].append([cell[0]+1,cell[1]+1])
        elif res.status == 'unknown':
            out['uncertain'].append([cell[0]+1,cell[1]+1])
    for cell in sorted(puzzle.crosses):
        if checked >= max_probes: break
        checked += 1
        res = solver.solve(crosses={cell})
        if res.status == 'unsat':
            out['invalid_crosses'].append([cell[0]+1,cell[1]+1])
        elif res.status == 'unknown':
            out['uncertain'].append([cell[0]+1,cell[1]+1])
    out['reason'] = ('空盘有多个解；只报告单个标记已被证明不可能的位置。'
                     '如果未发现错误，依然可能是多个标记联合造成冲突；'
                     f'本次检查了 {checked} 个标记。')
    return out
