import unittest
from fractions import Fraction

from linear_system_review import parse, review


class LinearReviewTests(unittest.TestCase):
    def fixture(self, x2='0x1p+1'):
        return f'''LINEAR_AUDIT begin id=1 time=0x1p-10 delta=0x1p-60 iteration=1 order=1 size=2 external=2 gmin=0x0p+0
LINEAR_AUDIT a id=1 row=1 col=1 value=0x1p+1
LINEAR_AUDIT a id=1 row=1 col=2 value=0x1p+0
LINEAR_AUDIT a id=1 row=2 col=2 value=0x1p+0
LINEAR_AUDIT b id=1 row=1 value=0x1p+2
LINEAR_AUDIT b id=1 row=2 value=0x1p+1
LINEAR_AUDIT name id=1 index=1 name=node
LINEAR_AUDIT name id=1 index=2 name=source#branch
LINEAR_AUDIT x id=1 row=1 value=0x1p+0
LINEAR_AUDIT x id=1 row=2 value={x2}
LINEAR_AUDIT end id=1
'''

    def test_exact_and_perturbed_solution(self):
        systems, incomplete = parse(self.fixture())
        self.assertEqual(incomplete, [])
        self.assertEqual(review(systems[0])['normwiseBackwardError'], 0)
        systems, _ = parse(self.fixture('0x1.0000000000001p+1'))
        result = review(systems[0])
        self.assertEqual(Fraction(result['worstAbsoluteResidual']['exactResidual']), Fraction(1, 2**51))
        self.assertEqual(result['worstComponentwiseResidual']['name'], 'source#branch')

    def test_reject_unaccounted_load_and_missing_data(self):
        for text in [self.fixture().replace('gmin=0x0p+0', 'gmin=0x1p-30'),
                     self.fixture().replace('size=2 external=2', 'size=2 external=3'),
                     self.fixture().replace('LINEAR_AUDIT x id=1 row=1 value=0x1p+0\n', '')]:
            with self.assertRaises(ValueError):
                parse(text)

    def test_incomplete_factorization_is_reported_separately(self):
        text = self.fixture()+self.fixture().replace('id=1', 'id=2').replace('LINEAR_AUDIT end id=2\n', '')
        systems, incomplete = parse(text)
        self.assertEqual(len(systems), 1)
        self.assertEqual(incomplete, [2])


if __name__ == '__main__':
    unittest.main()
