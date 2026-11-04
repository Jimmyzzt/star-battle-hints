import json
import unittest
from pathlib import Path

from starbattle import Puzzle, StarBattleSolver, next_hint, diagnose
from starbattle.model import fmt

DATA = Path(__file__).resolve().parent.parent/'examples'/'6x6-1star-demo.json'


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.obj = json.loads(DATA.read_text('utf-8'))
        self.puzzle = Puzzle.from_dict(self.obj)
        self.solver = StarBattleSolver(self.puzzle, time_limit=10.)

    def test_solve_and_validate(self):
        res = self.solver.with_marks()
        self.assertEqual(res.status, 'sat')
        self.solver.validate(res.solution)
        self.assertEqual(len(res.solution),6)
        self.assertIn((0,0),res.solution)

    def test_coordinates(self):
        self.assertEqual(fmt((0,0)),'R1C1')
        self.assertEqual(fmt((5,5)),'R6C6')

    def test_parse_errors(self):
        bad = dict(self.obj)
        bad['stars'] = [[1,1],[1,1]]
        with self.assertRaisesRegex(ValueError, 'duplicated'):
            Puzzle.from_dict(bad)
        bad['stars'] = [[1,2]]
        with self.assertRaisesRegex(ValueError, 'both'):
            Puzzle.from_dict(bad)
        bad['stars'] = []
        bad['regions'] = self.obj['regions'][:-1]+['AAAAAA']
        with self.assertRaisesRegex(ValueError, 'exactly'):
            Puzzle.from_dict(bad)

    def test_count_and_2x2(self):
        p = Puzzle.from_dict({**self.obj, 'stars':[[1,1],[2,2]], 'crosses':[]})
        self.assertEqual(StarBattleSolver(p).with_marks().status, 'unsat')
        p2 = Puzzle.from_dict({**self.obj, 'stars':[[1,1],[1,4]], 'crosses':[]})
        self.assertEqual(StarBattleSolver(p2).with_marks().status, 'unsat')

    def test_hint_first_step(self):
        # A star at (1,1) requires crossing R2C2 if it is unmarked.
        p = Puzzle.from_dict({**self.obj, 'crosses':[]})
        hint = next_hint(p, StarBattleSolver(p),level=2)
        self.assertEqual(hint['type'],'cross')
        self.assertIn(hint['cell'], ([1,2],[1,3],[1,4],[1,5],[1,6],[2,1],[2,2]))
        hint1 = next_hint(p, StarBattleSolver(p),level=1)
        self.assertIsNone(hint1['cell'])

    def test_check_reports_obvious_wrong_star(self):
        # A column marked full of forced stars makes the puzzle unsatisfiable.
        p = Puzzle.from_dict({**self.obj, 'stars':[[1,1],[2,1]], 'crosses':[]})
        out = diagnose(p, StarBattleSolver(p))
        self.assertEqual(out['status'], 'unsat')
        # Non-unique demo: no arbitrary comparison with just one solution.
        self.assertEqual(out['puzzle_uniqueness'], 'multiple')

    def test_disconnected_region_warning(self):
        bad = dict(self.obj)
        bad['regions'] = ['ABBBBB','BAAAAA','CCCCCC','DDDDDD','EEEEEE','FFFFFF']
        # This case retains 6 labels, some disjoint, and should be warned only.
        p = Puzzle.from_dict(bad)
        self.assertTrue(p.disconnected_regions())

    def test_exclude_solution(self):
        initial = self.solver.solve()
        different = self.solver.solve(exclude_solution=initial.solution)
        self.assertEqual(different.status, 'sat')
        self.assertNotEqual(initial.solution, different.solution)


if __name__ == '__main__':
    unittest.main()

class RealPuzzleRegressionTests(unittest.TestCase):
    """Real 17x17 / 4-star marking regression; no screenshots required in CI."""

    @classmethod
    def setUpClass(cls):
        path = DATA.parent/'2026-11-04-17x17-4star-transcribed.json'
        cls.puzzle = Puzzle.from_dict(json.loads(path.read_text('utf-8')))
        cls.solver = StarBattleSolver(cls.puzzle, time_limit=30.)

    def test_17x17_4star_confirmed_mismarks(self):
        self.assertEqual(self.puzzle.size, 17)
        self.assertEqual(self.puzzle.stars_per_unit, 4)
        self.assertEqual(len(self.puzzle.stars), 57)
        self.assertEqual(len(self.puzzle.crosses), 207)
        self.assertFalse(self.puzzle.disconnected_regions())
        out = diagnose(self.puzzle, self.solver)
        self.assertEqual(out['puzzle_uniqueness'], 'unique')
        self.assertEqual(out['status'], 'unsat')
        self.assertEqual(out['invalid_stars'], [[8,13],[10,13],[12,14],[16,15]])
        self.assertEqual(out['invalid_crosses'], [[11,13],[11,15],[13,14]])

    def test_hint_after_retracting_mismarks(self):
        bad_stars = {(7,12),(9,12),(11,13),(15,14)}
        bad_x = {(10,12),(10,14),(12,13)}
        from dataclasses import replace
        p = replace(self.puzzle,
                    stars=self.puzzle.stars-bad_stars,
                    crosses=self.puzzle.crosses-bad_x)
        s = StarBattleSolver(p,time_limit=30.)
        self.assertEqual(s.with_marks().status, 'sat')
        hint=next_hint(p,s,level=2)
        self.assertIn(hint['type'], ('star','cross'))


class HintLadderTests(unittest.TestCase):
    """Multi-step hints must never classify optional stars as forced."""

    def test_ladder_forced_stars_are_genuinely_forced(self):
        from dataclasses import replace
        from starbattle.ladder import hint_ladder
        path = DATA.parent/'2026-11-04-17x17-4star-transcribed.json'
        raw = Puzzle.from_dict(json.loads(path.read_text('utf-8')))
        p = replace(raw,
                    stars=raw.stars-{(7,12),(9,12),(11,13),(15,14)},
                    crosses=raw.crosses-{(10,12),(10,14),(12,13)})
        solver = StarBattleSolver(p, time_limit=30.)
        out = hint_ladder(p, solver, steps=3)
        self.assertEqual(out['status'], 'sat')
        self.assertTrue(out['steps'])
        for step in out['steps']:
            self.assertIn('tier1', step)
            self.assertIn('tier2', step)
            self.assertIn('tier3', step)
            for row, col in step['tier3']['forced_stars']:
                candidate = (row-1,col-1)
                proof = solver.solve(stars=p.stars, crosses=p.crosses | {candidate})
                self.assertEqual(proof.status, 'unsat')

    def test_ladder_rejects_contradictory_marks(self):
        from starbattle.ladder import hint_ladder
        p = Puzzle.from_dict({**json.loads(DATA.read_text('utf-8')),
                              'stars': [[1, 1], [2, 2]], 'crosses': []})
        out = hint_ladder(p, StarBattleSolver(p), steps=2)
        self.assertEqual(out['status'], 'unsat')
        self.assertEqual(out['steps'], [])
