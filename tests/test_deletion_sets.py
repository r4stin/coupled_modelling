import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from main import partition_subtree


def graph(*edges):
    """children map over the nodes reachable from 'root' (every node listed gets an entry)."""
    children = {}
    for subject, obj in edges:
        children.setdefault(subject, set()).add(obj)
        children.setdefault(obj, set())
    return children


class TestPartitionSubtree(unittest.TestCase):
    """Hermetic checks of the owned/kept split (no GraphDB)."""

    def test_chain_is_owned_entirely(self):
        owned, kept, referrers = partition_subtree('root', graph(('root', 'a'), ('a', 'b')), [])
        self.assertEqual(owned, ['root', 'a', 'b'])
        self.assertEqual((kept, referrers), ([], []))

    def test_anchor_and_its_descendants_are_kept(self):
        children = graph(('root', 'a'), ('a', 's'), ('s', 'd'))
        owned, kept, referrers = partition_subtree('root', children, [('x', 's'), ('a', 's')])
        self.assertEqual(owned, ['root', 'a'])
        self.assertEqual(kept, ['d', 's'])
        self.assertEqual(referrers, [])

    def test_diamond_is_listed_once(self):
        children = graph(('root', 'a'), ('root', 'b'), ('a', 'c'), ('b', 'c'))
        owned, kept, _ = partition_subtree('root', children, [])
        self.assertEqual(owned, ['root', 'a', 'b', 'c'])
        self.assertEqual(kept, [])

    def test_back_link_to_root_never_keeps_the_root_or_its_exclusive_children(self):
        children = graph(('root', 'a'), ('root', 's'), ('s', 'root'))
        owned, kept, referrers = partition_subtree('root', children, [('x', 's'), ('s', 'root')])
        self.assertEqual(owned, ['root', 'a'])
        self.assertEqual(kept, ['s'])
        # The kept node's link to the root is removed too, so it is reported.
        self.assertEqual(referrers, ['s'])

    def test_boundaries_are_kept_and_never_expanded(self):
        children = graph(('root', 'a'), ('a', 'cs'))
        owned, kept, referrers = partition_subtree('root', children, [], boundaries={'cs'})
        self.assertEqual(owned, ['root', 'a'])
        self.assertEqual(kept, ['cs'])
        self.assertEqual(referrers, [])

    def test_a_boundary_link_into_the_subtree_protects_its_target(self):
        children = graph(('root', 'a'), ('root', 'b'), ('a', 's'), ('b', 's'))
        owned, kept, _ = partition_subtree('root', children, [('root', 'a'), ('root', 'b'), ('a', 's'), ('b', 's')], boundaries={'b'})
        self.assertEqual(owned, ['root', 'a'])
        self.assertEqual(kept, ['b', 's'])

    def test_non_cascade_reports_every_surviving_referrer(self):
        owned, kept, referrers = partition_subtree('root', {'root': set()}, [('p', 'root'), ('root', 'root')])
        self.assertEqual((owned, kept, referrers), (['root'], [], ['p']))

    def test_cycle_inside_the_subtree_terminates(self):
        children = graph(('root', 'a'), ('a', 'b'), ('b', 'a'))
        owned, kept, _ = partition_subtree('root', children, [('b', 'a'), ('a', 'b')])
        self.assertEqual(owned, ['root', 'a', 'b'])
        self.assertEqual(kept, [])

    def test_node_reachable_from_an_anchor_is_kept_even_if_also_owned_path_exists(self):
        children = graph(('root', 'a'), ('a', 'c'), ('root', 's'), ('s', 'c'))
        owned, kept, _ = partition_subtree('root', children, [('x', 's')])
        self.assertEqual(owned, ['root', 'a'])
        self.assertEqual(kept, ['c', 's'])

    def test_outside_links_to_the_root_are_reported(self):
        owned, kept, referrers = partition_subtree('root', graph(('root', 'a')), [('p', 'root'), ('q', 'root')])
        self.assertEqual(owned, ['root', 'a'])
        self.assertEqual(kept, [])
        self.assertEqual(referrers, ['p', 'q'])


if __name__ == '__main__':
    unittest.main()
