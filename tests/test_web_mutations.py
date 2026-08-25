import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

import unittest
import uuid as uuid_mod
from unittest.mock import patch
import main
from main import GraphDBError
from api import app

class TestWebMutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run_id = uuid_mod.uuid4().hex[:8]
        cls.test_prefix = f"instance_test_m6_{run_id}_"
        cls.test_inst = f"instance_test_m6_subject_{run_id}"
        cls.test_obj = f"instance_test_m6_object_{run_id}"
        cls.onto_uri = "http://coupled_modelling.owl"
        
        # Patch main.instance_name to use our test-run prefix
        cls.original_instance_name = main.instance_name
        def mock_instance_name(use_uuid=True):
            if use_uuid:
                import uuid as u
                return f"{cls.test_prefix}{u.uuid4()}"
            return cls.original_instance_name(use_uuid=False)
            
        cls.patcher = patch('main.instance_name', side_effect=mock_instance_name)
        cls.patcher.start()
        cls.addClassCleanup(cls.patcher.stop)
        
        cls.clear_test_resources()

        init_query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        INSERT DATA {{
            GRAPH <{cls.onto_uri}> {{
                <http://coupled_modelling.owl#{cls.test_inst}> rdf:type <http://coupled_modelling.owl#solver_settings> .
                <http://coupled_modelling.owl#{cls.test_inst}> <http://coupled_modelling.owl#has_name> "TestSubject"^^xsd:string .
                <http://coupled_modelling.owl#{cls.test_inst}> <http://coupled_modelling.owl#has_echo_level> "2"^^xsd:integer .
                <http://coupled_modelling.owl#{cls.test_inst}> <http://coupled_modelling.owl#has_connect_to> <http://coupled_modelling.owl#{cls.test_obj}> .
                
                <http://coupled_modelling.owl#{cls.test_obj}> rdf:type <http://coupled_modelling.owl#solver> .
                <http://coupled_modelling.owl#{cls.test_obj}> <http://coupled_modelling.owl#has_name> "ExistingObject"^^xsd:string .
            }}
        }}
        """
        try:
            main.sparql_update(init_query)
        except Exception as e:
            raise unittest.SkipTest(f"GraphDB not available or failed setup: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.clear_test_resources()

    @classmethod
    def clear_test_resources(cls):
        query_find = f"""
        SELECT DISTINCT ?res WHERE {{
            GRAPH <{cls.onto_uri}> {{
                ?res ?p ?o .
                FILTER(isIRI(?res))
                FILTER(STRSTARTS(STR(?res), "http://coupled_modelling.owl#{cls.test_prefix}"))
            }}
        }}
        """
        resources_to_delete = [cls.test_inst, cls.test_obj]
        try:
            res = main.query_graphdb(query_find)
            bindings = res.get("results", {}).get("bindings", [])
            for b in bindings:
                local_name = main.get_local_name(b["res"]["value"])
                if local_name not in [cls.test_inst, cls.test_obj]:
                    resources_to_delete.append(local_name)
        except Exception:
            pass

        operations = []
        for res in resources_to_delete:
            operations.append(f"""
            DELETE WHERE {{
                GRAPH <{cls.onto_uri}> {{
                    <http://coupled_modelling.owl#{res}> ?p ?o .
                }}
            }}
            """)
            operations.append(f"""
            DELETE WHERE {{
                GRAPH <{cls.onto_uri}> {{
                    ?s ?p <http://coupled_modelling.owl#{res}> .
                }}
            }}
            """)
        
        if operations:
            query = " ; ".join(operations)
            try:
                main.sparql_update(query)
            except Exception:
                pass

    def setUp(self):
        self.app = app.test_client()

    def test_create_class_instance_success(self):
        payload = {
            "class": "solver",
            "label": "My New Standalone Solver"
        }
        res = self.app.post('/api/v1.0/create_class_instance/', json=payload)
        self.assertEqual(res.status_code, 201)
        new_name = res.get_json()
        self.assertTrue(new_name.startswith(self.test_prefix))

        # Query GraphDB to confirm
        query = f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{new_name}> rdf:type <http://coupled_modelling.owl#solver> .
                <http://coupled_modelling.owl#{new_name}> <http://www.w3.org/2000/01/rdf-schema#label> "My New Standalone Solver"^^xsd:string .
            }}
        }}
        """
        res_ask = main.query_graphdb(query)
        self.assertTrue(res_ask.get("boolean", False))

    def test_create_class_instance_missing_args(self):
        payload = {"class": "solver"}
        res = self.app.post('/api/v1.0/create_class_instance/', json=payload)
        self.assertEqual(res.status_code, 400)

    def test_create_class_instance_invalid_class(self):
        payload = {"class": "non_existent_class", "label": "Test"}
        res = self.app.post('/api/v1.0/create_class_instance/', json=payload)
        self.assertEqual(res.status_code, 400)

    def test_delete_value_literal_success(self):
        payload = {
            "instance": self.test_inst,
            "property": "echo_level",
            "value": {
                "kind": "literal",
                "value": 2,
                "datatype": "http://www.w3.org/2001/XMLSchema#integer"
            }
        }
        # First verify it is there
        query_before = f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_echo_level> "2"^^xsd:integer .
            }}
        }}
        """
        self.assertTrue(main.query_graphdb(query_before).get("boolean", False))

        # Run deletion
        res = self.app.post('/api/v1.0/delete_value/', json=payload)
        self.assertEqual(res.status_code, 201)

        # Confirm deleted
        self.assertFalse(main.query_graphdb(query_before).get("boolean", False))

    def test_delete_value_object_success(self):
        payload = {
            "instance": self.test_inst,
            "property": "connect_to",
            "value": {
                "kind": "object",
                "id": self.test_obj
            }
        }
        # First verify it is there
        query_before = f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_connect_to> <http://coupled_modelling.owl#{self.test_obj}> .
            }}
        }}
        """
        self.assertTrue(main.query_graphdb(query_before).get("boolean", False))

        # Run deletion
        res = self.app.post('/api/v1.0/delete_value/', json=payload)
        self.assertEqual(res.status_code, 201)

        # Confirm deleted
        self.assertFalse(main.query_graphdb(query_before).get("boolean", False))

    def test_delete_value_validation_subject_missing(self):
        payload = {
            "instance": "instance_does_not_exist",
            "property": "echo_level",
            "value": {
                "kind": "literal",
                "value": 2,
                "datatype": "http://www.w3.org/2001/XMLSchema#integer"
            }
        }
        res = self.app.post('/api/v1.0/delete_value/', json=payload)
        self.assertEqual(res.status_code, 400)

    def test_delete_value_dangling_object_reference_allowed(self):
        # Contract change: deleting a link whose target no longer exists must succeed —
        # it is the recovery operation for dangling references, so the existence check
        # that guards additions does not apply to deletions.
        payload = {
            "instance": self.test_inst,
            "property": "connect_to",
            "value": {
                "kind": "object",
                "id": "instance_does_not_exist"
            }
        }
        res = self.app.post('/api/v1.0/delete_value/', json=payload)
        self.assertEqual(res.status_code, 201)

    def test_replace_value_missing_params(self):
        res = self.app.post('/api/v1.0/replace_value/', json={"instance": self.test_inst, "property": "echo_level"})
        self.assertEqual(res.status_code, 400)

    def test_replace_value_literal_success(self):
        # Seed a value to replace.
        main.sparql_update(f"""
        INSERT DATA {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_parallel_type> "OpenMP" .
            }}
        }}
        """)
        payload = {
            "instance": self.test_inst,
            "property": "parallel_type",
            "old_value": {"kind": "literal", "value": "OpenMP", "datatype": "http://www.w3.org/2001/XMLSchema#string"},
            "new_value": {"kind": "literal", "value": "MPI", "datatype": "http://www.w3.org/2001/XMLSchema#string"},
        }
        res = self.app.post('/api/v1.0/replace_value/', json=payload)
        self.assertEqual(res.status_code, 201)

        query_new = f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_parallel_type> "MPI" .
            }}
        }}
        """
        query_old = query_new.replace('"MPI"', '"OpenMP"')
        self.assertTrue(main.query_graphdb(query_new).get("boolean", False))
        self.assertFalse(main.query_graphdb(query_old).get("boolean", False))

    def test_replace_value_missing_old_value_is_noop(self):
        # Replacing a value that is not stored must not insert the new value.
        payload = {
            "instance": self.test_inst,
            "property": "parallel_type",
            "old_value": {"kind": "literal", "value": "never_existed", "datatype": "http://www.w3.org/2001/XMLSchema#string"},
            "new_value": {"kind": "literal", "value": "ghost", "datatype": "http://www.w3.org/2001/XMLSchema#string"},
        }
        res = self.app.post('/api/v1.0/replace_value/', json=payload)
        self.assertEqual(res.status_code, 201)
        query_ghost = f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_parallel_type> "ghost" .
            }}
        }}
        """
        self.assertFalse(main.query_graphdb(query_ghost).get("boolean", False))

    def test_replace_value_preserves_language_tag(self):
        main.sparql_update(f"""
        INSERT DATA {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_comment> "Ein Loeser"@de .
            }}
        }}
        """)
        payload = {
            "instance": self.test_inst,
            "property": "comment",
            "old_value": {"kind": "literal", "value": "Ein Loeser", "language": "de"},
            "new_value": {"kind": "literal", "value": "Ein Solver", "language": "de"},
        }
        res = self.app.post('/api/v1.0/replace_value/', json=payload)
        self.assertEqual(res.status_code, 201)
        query_new = f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_comment> "Ein Solver"@de .
            }}
        }}
        """
        self.assertTrue(main.query_graphdb(query_new).get("boolean", False))

    def test_download_owl_success(self):
        res = self.app.get('/api/v1.0/download_owl/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/rdf+xml")
        self.assertIn("attachment", res.headers.get("Content-Disposition", ""))
        self.assertTrue(len(res.data) > 0)

    def test_database_error_503(self):
        # Patch query_graphdb to raise GraphDBError
        with patch('main.sparql_update', side_effect=GraphDBError("Connection timeout")):
            payload = {
                "class": "solver",
                "label": "Fail Solver"
            }
            res = self.app.post('/api/v1.0/create_class_instance/', json=payload)
            self.assertEqual(res.status_code, 503)

    def test_delete_instance_missing_param(self):
        res = self.app.post('/api/v1.0/delete_instance/', json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_delete_instance_success(self):
        create_res = self.app.post('/api/v1.0/create_class_instance/', json={
            "class": "solvers",
            "label": "ToDeleteInstance"
        })
        self.assertEqual(create_res.status_code, 201)
        inst_id = create_res.get_json()

        delete_res = self.app.post('/api/v1.0/delete_instance/', json={
            "instance": inst_id
        })
        self.assertEqual(delete_res.status_code, 200)
        self.assertEqual(delete_res.get_json().get("status"), "success")
        self.assertEqual(delete_res.get_json().get("instance"), inst_id)
        self.assertFalse(main.instance_exists(inst_id))

    def test_add_values_accepts_literal_on_datatype_property(self):
        payload = {
            "instance": self.test_inst,
            "data": {"num_coupling_iterations": 12}
        }
        res = self.app.post('/api/v1.0/add_values/', json=payload)
        self.assertEqual(res.status_code, 201)

        query = f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_num_coupling_iterations> "12"^^xsd:integer .
            }}
        }}
        """
        self.assertTrue(main.query_graphdb(query).get("boolean", False))

    def test_add_values_resolves_label_to_existing_instance(self):
        # Labels resolve globally, so keep them unique per test run: a leftover
        # from a crashed or concurrent run must not be able to satisfy LIMIT 1.
        label = f"Existing Label Target {self.test_prefix}"
        create_res = self.app.post('/api/v1.0/create_class_instance/', json={
            "class": "solver",
            "label": label
        })
        self.assertEqual(create_res.status_code, 201)
        target_id = create_res.get_json()

        res = self.app.post('/api/v1.0/add_values/', json={
            "instance": self.test_inst,
            "data": {"solver": label}
        })
        self.assertEqual(res.status_code, 201)

        query = f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_solver> <http://coupled_modelling.owl#{target_id}> .
            }}
        }}
        """
        self.assertTrue(main.query_graphdb(query).get("boolean", False))

    def test_add_values_creates_labeled_instance_for_unknown_label(self):
        label = f"Brand New Label Target {self.test_prefix}"
        res = self.app.post('/api/v1.0/add_values/', json={
            "instance": self.test_inst,
            "data": {"solver": label}
        })
        self.assertEqual(res.status_code, 201)

        query = f"""
        SELECT ?obj WHERE {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_solver> ?obj .
                ?obj rdf:type <http://coupled_modelling.owl#solver> .
                ?obj <http://www.w3.org/2000/01/rdf-schema#label> "{label}"^^xsd:string .
            }}
        }}
        """
        bindings = main.query_graphdb(query).get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 1)
        new_ref = main.get_local_name(bindings[0]["obj"]["value"])
        self.assertTrue(new_ref.startswith(self.test_prefix))

    def test_add_values_resolves_each_label_in_a_list(self):
        labels = [f"List Label A {self.test_prefix}", f"List Label B {self.test_prefix}"]
        res = self.app.post('/api/v1.0/add_values/', json={
            "instance": self.test_inst,
            "data": {"solver": labels}
        })
        self.assertEqual(res.status_code, 201)

        query = f"""
        SELECT ?label WHERE {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_solver> ?obj .
                ?obj <http://www.w3.org/2000/01/rdf-schema#label> ?label .
                FILTER(STRSTARTS(STR(?label), "List Label"))
            }}
        }}
        """
        bindings = main.query_graphdb(query).get("results", {}).get("bindings", [])
        self.assertEqual(sorted(b["label"]["value"] for b in bindings), labels)

    def test_add_values_rejects_null_values(self):
        res = self.app.post('/api/v1.0/add_values/', json={
            "instance": self.test_inst,
            "data": {"echo_level": None}
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_add_values_rejects_missing_instance_reference(self):
        res = self.app.post('/api/v1.0/add_values/', json={
            "instance": self.test_inst,
            "data": {"solver": "instance_does_not_exist_999"}
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn("does not exist", res.get_json().get("error", ""))

    def test_add_values_invalid_reference_inserts_nothing(self):
        orphan_label = f"Orphan Candidate {self.test_prefix}"
        res = self.app.post('/api/v1.0/add_values/', json={
            "instance": self.test_inst,
            "data": {
                "num_coupling_iterations": 77,
                "solver": [orphan_label, "instance_does_not_exist_999"]
            }
        })
        self.assertEqual(res.status_code, 400)

        query = f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_inst}> <http://coupled_modelling.owl#has_num_coupling_iterations> "77"^^xsd:integer .
            }}
        }}
        """
        self.assertFalse(main.query_graphdb(query).get("boolean", False))

        # The label that would have been resolved-or-created must not leave an
        # orphan instance behind when the request fails validation.
        orphan_query = f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                ?inst <http://www.w3.org/2000/01/rdf-schema#label> "{orphan_label}"^^xsd:string .
            }}
        }}
        """
        self.assertFalse(main.query_graphdb(orphan_query).get("boolean", False))

if __name__ == '__main__':
    unittest.main()
