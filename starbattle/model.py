"""Puzzle schema, strict validation, and cell/region helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Cell = tuple[int, int]  # internally 0-based


def fmt(cell: Cell) -> str:
    return f"R{cell[0] + 1}C{cell[1] + 1}"


def parse_cells(values: Any, name: str, size: int) -> frozenset[Cell]:
    if not isinstance(values, list):
        raise ValueError(f"{name} must be an array of [row, column] pairs")
    out = set()
    for value in values:
        if (not isinstance(value, (list, tuple)) or len(value) != 2 or
                not all(type(i) is int for i in value)):
            raise ValueError(f"{name} entry must be [row, column]: {value!r}")
        r, c = value
        if not (1 <= r <= size and 1 <= c <= size):
            raise ValueError(f"{name}: coordinate outside 1..{size}: {value!r}")
        cell = (r-1, c-1)
        if cell in out:
            raise ValueError(f"{name}: duplicated cell {fmt(cell)}")
        out.add(cell)
    return frozenset(out)


@dataclass(frozen=True)
class Puzzle:
    size: int
    stars_per_unit: int
    regions: tuple[tuple[str, ...], ...]
    stars: frozenset[Cell] = frozenset()
    crosses: frozenset[Cell] = frozenset()

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> Puzzle:
        n, k = obj.get('size'), obj.get('stars_per_unit')
        if type(n) is not int or not (2 <= n <= 50):
            raise ValueError('size must be an integer between 2 and 50')
        if type(k) is not int or not (1 <= k <= n):
            raise ValueError('stars_per_unit must be an integer in 1..size')
        raw = obj.get('regions')
        if not isinstance(raw, list) or len(raw) != n:
            raise ValueError(f'regions must contain {n} rows')
        rows = []
        for row in raw:
            if isinstance(row, str):
                labels = tuple(row)
            elif isinstance(row, list) and all(isinstance(s, str) and s for s in row):
                labels = tuple(row)
            else:
                raise ValueError('each region row must be a string or list of labels')
            if len(labels) != n:
                raise ValueError(f'each region row must have {n} cells')
            rows.append(labels)
        labels = {tag for row in rows for tag in row}
        if len(labels) != n:
            raise ValueError(f'expected exactly {n} regions, got {len(labels)}')
        for tag in labels:
            if sum(cell == tag for row in rows for cell in row) < k:
                raise ValueError(f'region {tag!r} has fewer than {k} cells')
        stars = parse_cells(obj.get('stars', []), 'stars', n)
        crosses = parse_cells(obj.get('crosses', []), 'crosses', n)
        if stars & crosses:
            raise ValueError(f'cell cannot be both star and cross: {fmt(min(stars & crosses))}')
        return cls(n, k, tuple(rows), stars, crosses)

    def unit_groups(self) -> list[tuple[str, tuple[Cell, ...]]]:
        n = self.size
        groups = []
        for r in range(n):
            groups.append((f'第 {r + 1} 行', tuple((r, c) for c in range(n))))
        for c in range(n):
            groups.append((f'第 {c + 1} 列', tuple((r, c) for r in range(n))))
        labels = sorted({tag for row in self.regions for tag in row})
        for tag in labels:
            groups.append((f'区域 {tag}', tuple((r, c) for r in range(n)
                    for c in range(n) if self.regions[r][c] == tag)))
        return groups

    def disconnected_regions(self) -> list[str]:
        """A warning for likely screenshot transcription mistakes (not a hard error)."""
        groups = self.unit_groups()[2*self.size:]
        disconnected = []
        for name, cells in groups:
            unvisited = set(cells)
            seen = {next(iter(unvisited))}
            stack = list(seen)
            while stack:
                r, c = stack.pop()
                for q in ((r-1,c),(r+1,c),(r,c-1),(r,c+1)):
                    if q in unvisited and q not in seen:
                        seen.add(q)
                        stack.append(q)
            if seen != unvisited:
                disconnected.append(name)
        return disconnected

    def nearby(self, cell: Cell) -> set[Cell]:
        r, c = cell
        n = self.size
        return {(rr, cc) for rr in range(max(0,r-1),min(n,r+2))
                  for cc in range(max(0,c-1),min(n,c+2)) if (rr,cc)!=cell}
