import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from main import partition_subtree, partition_unlinked


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


class TestPartitionUnlinked(unittest.TestCase):
    """Hermetic checks of the unlink split (no GraphDB). `incoming` never holds the removed link h -> t."""

    def test_orphaned_target_is_collected_with_its_subtree(self):
        owned, kept = partition_unlinked('h', 't', graph(('t', 'a'), ('a', 'b')), [('t', 'a'), ('a', 'b')])
        self.assertEqual((owned, kept), (['t', 'a', 'b'], []))

    def test_target_linked_from_elsewhere_survives_untouched(self):
        owned, kept = partition_unlinked('h', 't', graph(('t', 'a')), [('x', 't'), ('t', 'a')])
        self.assertEqual((owned, kept), ([], ['t']))

    def test_target_reached_through_a_kept_node_survives(self):
        children = graph(('t', 'a'), ('a', 's'), ('s', 't'))
        owned, kept = partition_unlinked('h', 't', children, [('x', 's'), ('a', 's'), ('s', 't'), ('t', 'a')])
        self.assertEqual((owned, kept), ([], ['t']))

    def test_boundary_target_survives(self):
        owned, kept = partition_unlinked('h', 't', {'t': set()}, [], boundaries={'t'})
        self.assertEqual((owned, kept), ([], ['t']))

    def test_shared_descendants_are_kept_when_the_target_is_collected(self):
        children = graph(('t', 'a'), ('a', 's'), ('s', 'd'))
        owned, kept = partition_unlinked('h', 't', children, [('t', 'a'), ('a', 's'), ('x', 's'), ('s', 'd')])
        self.assertEqual((owned, kept), (['t', 'a'], ['d', 's']))

    def test_holder_inside_the_subtree_survives_while_the_target_is_collected(self):
        # Only the target links to the holder: the holder is an anchor, never garbage.
        children = graph(('t', 'h'))
        owned, kept = partition_unlinked('h', 't', children, [('t', 'h')])
        self.assertEqual((owned, kept), (['t'], ['h']))

    def test_what_the_holder_still_reaches_is_kept(self):
        children = graph(('t', 'a'), ('t', 'h'), ('h', 'a'))
        owned, kept = partition_unlinked('h', 't', children, [('t', 'a'), ('t', 'h'), ('h', 'a')])
        self.assertEqual((owned, kept), (['t'], ['a', 'h']))

    def test_self_link_never_collects_the_holder(self):
        owned, kept = partition_unlinked('t', 't', {'t': set()}, [])
        self.assertEqual((owned, kept), ([], ['t']))

    def test_holder_reached_through_a_back_link_is_kept_and_does_not_block(self):
        children = graph(('t', 'a'), ('a', 'h'))
        owned, kept = partition_unlinked('h', 't', children, [('t', 'a'), ('a', 'h')])
        self.assertEqual((owned, kept), (['t', 'a'], ['h']))


if __name__ == '__main__':
    unittest.main()
