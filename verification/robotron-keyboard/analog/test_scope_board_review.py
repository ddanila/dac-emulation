import copy
import unittest
from scope_board_review import ScopeMembership, changed_scope
from test_code_binding_board_review import state as code_state


def state():
    result = code_state()
    pointers = sorted({t['scope'] for t in result['threads']['threads']})
    result['scopes'] = [dict(id=i+1, pointer=p, parent=0, kind=32,
                             members=sorted(t['id'] for t in result['threads']['threads'] if t['scope']==p))
                        for i,p in enumerate(pointers)]
    result['scopes'].append(dict(id=len(pointers)+1, pointer=0xDEAD, parent=1, kind=32, members=[]))
    return result


class ScopeBoard(unittest.TestCase):
    def test_membership_and_empty_scopes(self):
        tracker = ScopeMembership()
        tracker.observe(state())
        tracker.observe(state())
        self.assertEqual(tracker.result(False)['emptyScopeObservations'], 2)

    def test_missing_rebound_wrong_owner(self):
        for mode in ('missing', 'rebound', 'owner'):
            tracker = ScopeMembership()
            tracker.observe(state())
            bad = state()
            if mode == 'missing':
                bad['scopes'].pop()
            elif mode == 'rebound':
                bad['scopes'][-1]['pointer'] += 1
            else:
                bad['scopes'][-1]['members'] = [bad['scopes'][0]['members'][0]]
            with self.assertRaises(ValueError):
                tracker.observe(bad)

    def test_exact_fault_preserves_preceding_layers(self):
        before = state()
        after = copy.deepcopy(before)
        after['scopes'][0]['members'].pop(0)
        for name in ('startup', 'late'):
            changed_scope(before, after, name)
        after['threadCode'][0]['opcode'] += 1
        with self.assertRaises(ValueError):
            changed_scope(before, after, 'startup')


if __name__ == '__main__':
    unittest.main()
