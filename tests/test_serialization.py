import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

import unittest
from main import serialize_iri, serialize_literal, serialize_object, validate_local_name

class TestSerialization(unittest.TestCase):
    def test_validate_local_name(self):
        # Valid names
        validate_local_name("instance_123")
        validate_local_name("low_fid_fluid")
        validate_local_name("solver-wrapper")
        validate_local_name("solver.wrapper")
        
        # Invalid names
        with self.assertRaises(ValueError):
            validate_local_name("")
        with self.assertRaises(ValueError):
            validate_local_name("instance/123")
        with self.assertRaises(ValueError):
            validate_local_name("instance#123")
        with self.assertRaises(ValueError):
            validate_local_name("solver wrapper")
        with self.assertRaises(ValueError):
            validate_local_name("solver'wrapper")

    def test_serialize_iri(self):
        self.assertEqual(serialize_iri("instance_123"), "<http://coupled_modelling.owl#instance_123>")
        self.assertEqual(serialize_iri("low_fid_fluid"), "<http://coupled_modelling.owl#low_fid_fluid>")
        
        with self.assertRaises(ValueError):
            serialize_iri("instance/123")

    def test_serialize_literal_bool(self):
        self.assertEqual(serialize_literal(True), '"true"^^xsd:boolean')
        self.assertEqual(serialize_literal(False), '"false"^^xsd:boolean')

    def test_serialize_literal_int(self):
        self.assertEqual(serialize_literal(42), '"42"^^xsd:integer')
        self.assertEqual(serialize_literal(0), '"0"^^xsd:integer')
        self.assertEqual(serialize_literal(-1), '"-1"^^xsd:integer')

    def test_serialize_literal_float(self):
        self.assertEqual(serialize_literal(3.14), '"3.14"^^xsd:double')
        self.assertEqual(serialize_literal(0.0), '"0.0"^^xsd:double')

    def test_serialize_literal_str_escaping(self):
        self.assertEqual(serialize_literal("simple"), '"simple"^^xsd:string')
        # Backslash and quote escaping
        self.assertEqual(serialize_literal('solver "A"'), '"solver \\"A\\""^^xsd:string')
        self.assertEqual(serialize_literal('path\\to\\file'), '"path\\\\to\\\\file"^^xsd:string')
        # Control characters escaping
        self.assertEqual(serialize_literal("line1\nline2"), '"line1\\nline2"^^xsd:string')
        self.assertEqual(serialize_literal("cr\rrt"), '"cr\\rrt"^^xsd:string')
        self.assertEqual(serialize_literal("tab\tspace"), '"tab\\tspace"^^xsd:string')

    def test_serialize_literal_unsupported(self):
        with self.assertRaises(ValueError):
            serialize_literal([1, 2, 3])
        with self.assertRaises(ValueError):
            serialize_literal({"key": "value"})

    def test_serialize_object(self):
        # Instance names starting with "instance" should serialize as IRIs
        self.assertEqual(serialize_object("instance_42"), "<http://coupled_modelling.owl#instance_42>")
        
        # Standard strings should serialize as typed string literals
        self.assertEqual(serialize_object("some_string"), '"some_string"^^xsd:string')
        self.assertEqual(serialize_object("instance.foo"), "<http://coupled_modelling.owl#instance.foo>")
        
        # Other types should serialize as literals
        self.assertEqual(serialize_object(True), '"true"^^xsd:boolean')
        self.assertEqual(serialize_object(100), '"100"^^xsd:integer')
        self.assertEqual(serialize_object(2.5), '"2.5"^^xsd:double')

if __name__ == "__main__":
    unittest.main()
