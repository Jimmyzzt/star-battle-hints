"""Exact integer-programming model. No guessing from screenshot colors.

Binary x[r,c] in {0,1}. Every row, column and region sums to k;
every 2-by-2 block sums to <=1 (equivalent to no king-move touching).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import coo_matrix, vstack

from .model import Puzzle, Cell


@dataclass(frozen=True)
class SolveResult:
    status: str  # sat / unsat / unknown
    solution: frozenset[Cell] | None = None
    reason: str = ''


class StarBattleSolver:
    def __init__(self, puzzle: Puzzle, time_limit: float = 15.0):
        self.puzzle = puzzle
        self.n = puzzle.size
        self.time_limit = time_limit
        coefficients = []
        lower = []
        upper = []
        rr, cc, vv = [], [], []

        def add(cells: Iterable[Cell], low: int, high: int):
            i = len(lower)
            for r, c in cells:
                rr.append(i)
                cc.append(r*self.n+c)
                vv.append(1.)
            lower.append(float(low))
            upper.append(float(high))

        for _, cells in puzzle.unit_groups():
            add(cells, puzzle.stars_per_unit, puzzle.stars_per_unit)
        for r in range(self.n-1):
            for c in range(self.n-1):
                add(((r,c),(r+1,c),(r,c+1),(r+1,c+1)), 0, 1)
        self.matrix = coo_matrix((vv, (rr, cc)),
                                 shape=(len(lower), self.n*self.n)).tocsr()
        self.lower = np.asarray(lower)
        self.upper = np.asarray(upper)
        self.objective = np.zeros(self.n*self.n)
        self.integrality = np.ones(self.n*self.n)

    def solve(self, *, stars: Iterable[Cell] = (), crosses: Iterable[Cell] = (),
              exclude_solution: Iterable[Cell] | None = None) -> SolveResult:
        stars, crosses = frozenset(stars), frozenset(crosses)
        if stars & crosses:
            return SolveResult('unsat', reason='same cell both forced star and cross')
        lo = np.zeros(self.n*self.n)
        hi = np.ones(self.n*self.n)
        for r,c in stars: lo[r*self.n+c] = 1
        for r,c in crosses: hi[r*self.n+c] = 0
        if exclude_solution is None:
            constraint = LinearConstraint(self.matrix, self.lower, self.upper)
        else:
            sol = frozenset(exclude_solution)
            if len(sol) != self.n*self.puzzle.stars_per_unit:
                raise ValueError('exclude_solution must be a complete solution')
            # Given fixed total number of stars, this excludes exactly one solution.
            row = coo_matrix((np.ones(len(sol)),
                ([0]*len(sol), [r*self.n+c for r,c in sol])),
                shape=(1,self.n*self.n)).tocsr()
            constraint = LinearConstraint(vstack((self.matrix,row)),
                np.r_[self.lower, 0.], np.r_[self.upper,float(len(sol)-1)])
        result = milp(self.objective, integrality=self.integrality,
                      bounds=Bounds(lo,hi), constraints=constraint,
                      options={'time_limit': self.time_limit})
        if result.status == 2:
            return SolveResult('unsat', reason=str(result.message))
        if result.status != 0 or result.x is None:
            return SolveResult('unknown', reason=str(result.message))
        chosen = frozenset((i//self.n,i%self.n)
                           for i, value in enumerate(result.x) if value > .5)
        self.validate(chosen)
        return SolveResult('sat', chosen)

    def validate(self, sol: frozenset[Cell]):
        k = self.puzzle.stars_per_unit
        for name, unit in self.puzzle.unit_groups():
            if len(sol.intersection(unit)) != k:
                raise AssertionError(f'invalid solver output: {name}')
        for star in sol:
            if self.puzzle.nearby(star).intersection(sol):
                raise AssertionError('invalid solver output: touching stars')

    def with_marks(self) -> SolveResult:
        return self.solve(stars=self.puzzle.stars, crosses=self.puzzle.crosses)

    def uniqueness(self, solution: frozenset[Cell]) -> str:
        """unique / multiple / unknown, relative to the current marks."""
        r = self.solve(stars=self.puzzle.stars, crosses=self.puzzle.crosses,
                       exclude_solution=solution)
        return {'unsat':'unique','sat':'multiple','unknown':'unknown'}[r.status]
