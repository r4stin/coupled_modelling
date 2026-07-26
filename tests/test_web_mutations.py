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

    def test_delete_value_validation_object_missing(self):
        payload = {
            "instance": self.test_inst,
            "property": "connect_to",
            "value": {
                "kind": "object",
                "id": "instance_does_not_exist"
            }
        }
        res = self.app.post('/api/v1.0/delete_value/', json=payload)
        self.assertEqual(res.status_code, 400)

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

if __name__ == '__main__':
    unittest.main()
