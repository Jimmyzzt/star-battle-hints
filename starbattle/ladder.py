"""Precompute spoiler-tiered, provable local and two-unit hint steps.

A unit pattern satisfies its remaining star quota and no-touch constraints.
Combining two units relaxes the full puzzle, so common stars are forced.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from itertools import combinations
from math import comb

from .logic import _safe_cells
from .model import Puzzle
from .solver import StarBattleSolver


def _pairwise_forced(puzzle: Puzzle, possible: set, *,
                     max_combinations: int = 1200,
                     max_pair_products: int = 12000):
    """Find a sound deduction from one or two exact-count unit constraints.

    Units exceeding complete enumeration limits are skipped, not truncated.
    """
    units = puzzle.unit_groups()
    units = units[2*puzzle.size:] + units[:2*puzzle.size]
    fixed = set(puzzle.stars)
    k = puzzle.stars_per_unit
    groups = []
    tags = {v for row in puzzle.regions for v in row}
    quota_r = [k-sum(r==rr for r,c in fixed) for rr in range(puzzle.size)]
    quota_c = [k-sum(c==cc for r,c in fixed) for cc in range(puzzle.size)]
    quota_g = {tag:k-sum(puzzle.regions[r][c]==tag for r,c in fixed)
               for tag in tags}

    for name, cells in units:
        unit_set = set(cells)
        available = sorted(unit_set & possible)
        needed = k - len(fixed & unit_set)
        if not (1 <= needed <= len(available)):
            continue
        if comb(len(available), needed) > max_combinations:
            continue
        patterns = [frozenset(chosen) for chosen in combinations(available, needed)
                    if all(abs(x[0]-y[0])>1 or abs(x[1]-y[1])>1
                           for x,y in combinations(chosen,2))]
        if not patterns:
            continue
        intersection = set.intersection(*(set(x) for x in patterns))
        never = set(available) - set.union(*(set(x) for x in patterns))
        if intersection:
            return {'scope':name, 'needed':needed,
                    'pattern_count':len(patterns),
                    'forced':intersection, 'excluded':never, 'mode':'single'}
        groups.append((name, unit_set, needed, patterns))

    def valid_union(u):
        rc = Counter(r for r,c in u)
        cc = Counter(c for r,c in u)
        gc = Counter(puzzle.regions[r][c] for r,c in u)
        return (all(n<=quota_r[r] for r,n in rc.items())
                and all(n<=quota_c[c] for c,n in cc.items())
                and all(n<=quota_g[tag] for tag,n in gc.items()))

    best = None
    for a,b in combinations(groups,2):
        name_a,cells_a,needed_a,pats_a = a
        name_b,cells_b,needed_b,pats_b = b
        if len(pats_a)*len(pats_b)>max_pair_products:
            continue
        compatible = []
        for pa in pats_a:
            for pb in pats_b:
                both = pa | pb
                if (len(both & cells_a)!=needed_a or
                        len(both & cells_b)!=needed_b):
                    continue
                if any(x!=y and abs(x[0]-y[0])<=1 and abs(x[1]-y[1])<=1
                       for x in pa for y in pb):
                    continue
                if valid_union(both):
                    compatible.append(both)
        if not compatible:
            continue
        forced = set.intersection(*(set(z) for z in compatible))
        if not forced:
            continue
        candidate = {
            'scope': f'{name_a} + {name_b}',
            'needed': needed_a+needed_b,
            'pattern_count': len(compatible),
            'unit_pattern_counts': [len(pats_a),len(pats_b)],
            'forced': forced, 'excluded': set(), 'mode': 'pair',
        }
        def rank(z):
            a,b = z['scope'].split(' + ')
            if a.startswith('区域') and b.startswith('区域'):
                cls=0
            elif a.endswith('列') and b.endswith('列'):
                cls=1
            elif a.endswith('行') and b.endswith('行'):
                cls=2
            else:
                cls=3
            return (cls, z['pattern_count'])
        if best is None or rank(candidate)<rank(best):
            best = candidate
    return best


def hint_ladder(puzzle: Puzzle, solver: StarBattleSolver, *,
                steps: int = 3, max_combinations: int = 1200) -> dict:
    if not 1 <= steps <= 15:
        raise ValueError('steps must be 1..15')
    if not 1 <= max_combinations <= 100_000:
        raise ValueError('max_combinations must be 1..100000')
    state = solver.with_marks()
    if state.status != 'sat':
        return {'status': state.status, 'steps': [],
                'reason': '当前标记无解或求解未知；请先 check 并核对截图。'}
    working = puzzle
    results = []
    for _ in range(steps):
        info = _pairwise_forced(working, _safe_cells(working),
                                max_combinations=max_combinations)
        if info is None:
            break
        scope, pat_count = info['scope'], info['pattern_count']
        must, never = info['forced'], info['excluded']
        to_pairs = lambda cells: [[r+1,c+1] for r,c in sorted(cells)]
        if info['mode']=='single':
            tier2 = (f'{scope}还需要 {info["needed"]} 颗星。'
                     f'仅按此单元的数量与不相邻规则，共有 {pat_count} 种可行摆法。'
                     '寻找它们的交集。')
        else:
            tier2 = (f'将{scope}的局部摆法配对，并检查不相邻及每行、列、区域'
                     f'的容量上限，仅剩 {pat_count} 种兼容组合；找出共同出现的位置。')
        results.append({
            'scope': scope,
            'tier1': f'观察{scope}，把星数配额和不能相邻一起考虑。',
            'tier2': tier2,
            'tier3': {
                'forced_stars': to_pairs(must),
                'also_excluded': to_pairs(never),
                'proof': f'{pat_count} 种局部兼容摆法里，必放的格子在每种摆法中都出现。',
            },
            'method': info['mode'],
        })
        working = replace(working, stars=frozenset(working.stars | must),
                          crosses=frozenset(working.crosses | never))
    return {'status':'sat','steps':results,
            'disclosure':('JSON 包含全部三级结论；聊天 UI 应初始只显示 tier1，'
                          '只在用户点击时揭示 tier2、tier3。'),
            'reason':'每一条基于完备局部枚举；找不到下一步时停止，不虚构结论。'}
