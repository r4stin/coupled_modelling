import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

import unittest
from unittest.mock import patch
import main


class TestKratosImportHelpers(unittest.TestCase):
    """
    Pins the Owlready2 creation-path fixes: UUID instance names, kind-filtered
    label lookups, cycle-safe traversal, and child linking for empty payloads.
    All changes stay in memory and are discarded by reloading from GraphDB —
    which is also why the suite skips without GraphDB: without the reload the
    created test entities would leak into later suites in the same process.
    """

    @classmethod
    def setUpClass(cls):
        # reload_ontology_from_graphdb swallows connection errors, so probe
        # GraphDB with a call that actually raises when it is down.
        try:
            main.query_graphdb("ASK { ?s ?p ?o }")
        except Exception as e:
            raise unittest.SkipTest(f"GraphDB not available: {e}")
        main.reload_ontology_from_graphdb()

    @classmethod
    def tearDownClass(cls):
        # Discard every in-memory individual/class the tests created.
        main.reload_ontology_from_graphdb()

    def test_instance_name_is_free_in_the_loaded_ontology(self):
        name = main.instance_name()
        self.assertTrue(name.startswith("instance_"))
        self.assertIsNone(main.onto[name])

    def test_get_class_ignores_individuals_sharing_the_label(self):
        # The individual must exist BEFORE any class carries the label, so an
        # unfiltered lookup would return the individual.
        with main.onto:
            holder_cl = main.get_class('zz_test_label_holder')
            inst = holder_cl(main.instance_name())
            inst.label = ['zz_test_shared_label']

        resolved = main.get_class('zz_test_shared_label')
        self.assertIsInstance(resolved, main.ThingClass)
        self.assertIsNot(resolved, inst)

    def test_property_lookups_share_one_entity_per_name(self):
        with main.onto:
            data_prop = main.get_property('zz_test_mixed_kind')
            object_prop = main.get_relation('zz_test_mixed_kind')

        # One property entity per has_* name: the first-created kind wins and is
        # reused, never redeclared into both kinds (invalid OWL punning).
        self.assertIs(object_prop, data_prop)
        self.assertIsInstance(data_prop, main.DataPropertyClass)
        self.assertNotIn(main.ObjectProperty, data_prop.is_a)

    def test_str_to_inst_survives_a_class_sharing_the_label(self):
        with main.onto:
            holder_cl = main.get_class('zz_test_str_holder')
            holder = holder_cl(main.instance_name())
            # A class labeled exactly like the incoming string value.
            main.get_class('zz_test_str_value')
            main.str_to_inst(holder, 'zz_test_str_target', 'zz_test_str_value')

        rel = main.get_relation('zz_test_str_target')
        self.assertEqual(len(rel[holder]), 1)
        self.assertEqual(rel[holder][0].label, ['zz_test_str_value'])

    def test_dict_to_inst_links_children_with_empty_payloads(self):
        with main.onto:
            holder_cl = main.get_class('zz_test_dict_holder')
            holder = holder_cl(main.instance_name())
            main.dict_to_inst(holder, 'zz_test_dict_child', {})

        rel = main.get_relation('zz_test_dict_child')
        self.assertEqual(len(rel[holder]), 1)

    def test_export_keeps_value_strings_that_share_a_class_name(self):
        with main.onto:
            # Classes whose local names equal incoming string values (keys
            # become classes, so this happens across configurations).
            main.get_class('zz_test_collide_value')
            main.get_class('zz_test_collide_other')
            holder_cl = main.get_class('zz_test_export_root')
            holder = holder_cl(main.instance_name())
            # Scalar branch: one value; list branch: two values on one property.
            main.str_to_inst(holder, 'zz_test_export_link', 'zz_test_collide_value')
            main.str_to_inst(holder, 'zz_test_export_multi', 'zz_test_collide_value')
            main.str_to_inst(holder, 'zz_test_export_multi', 'zz_test_collide_other')

        # Force the in-memory property path so the in-memory fixture is used;
        # silence the fallback warning it prints per visited instance.
        with patch('main.query_graphdb', side_effect=main.GraphDBError('down')), patch('builtins.print'):
            exported = main.export_coupled_kratos(holder.name)

        self.assertEqual(exported.get('zz_test_export_link'), 'zz_test_collide_value')
        self.assertEqual(sorted(exported.get('zz_test_export_multi')), ['zz_test_collide_other', 'zz_test_collide_value'])

    def test_connected_instances_traversal_terminates_on_cycles(self):
        with main.onto:
            cl = main.get_class('zz_test_cycle_class')
            first = cl(main.instance_name())
            second = cl(main.instance_name())
            rel = main.get_relation('zz_test_cycle_link')
            rel[first].append(second)
            rel[second].append(first)

        insts = {}
        main.get_connected_instances_recursively(first.name, insts, 0)
        self.assertIn(main.onto[first.name], insts)
        self.assertIn(main.onto[second.name], insts)


if __name__ == '__main__':
    unittest.main()
