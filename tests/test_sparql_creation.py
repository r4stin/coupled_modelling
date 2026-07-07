import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

import unittest
import uuid as uuid_mod
from unittest.mock import patch
import main
from main import GraphDBError
from api import app

class TestSparqlCreation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run_id = uuid_mod.uuid4().hex[:8]
        cls.test_prefix = f"instance_test_m3_{run_id}_"
        cls.test_parent = f"instance_test_m3_parent_{run_id}"
        cls.test_obj = f"instance_test_m3_object_{run_id}"
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
        INSERT DATA {{
            GRAPH <{cls.onto_uri}> {{
                <http://coupled_modelling.owl#{cls.test_parent}> rdf:type <http://coupled_modelling.owl#solver_settings> .
                <http://coupled_modelling.owl#{cls.test_parent}> <http://coupled_modelling.owl#has_name> "ParentSolverSettings"^^xsd:string .
                
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
        # Query GraphDB for all instances generated under our unique test run prefix
        query_find = f"""
        SELECT DISTINCT ?res WHERE {{
            GRAPH <{cls.onto_uri}> {{
                ?res ?p ?o .
                FILTER(isIRI(?res))
                FILTER(STRSTARTS(STR(?res), "http://coupled_modelling.owl#{cls.test_prefix}"))
            }}
        }}
        """
        resources_to_delete = [cls.test_parent, cls.test_obj]
        try:
            res = main.query_graphdb(query_find)
            bindings = res.get("results", {}).get("bindings", [])
            for b in bindings:
                local_name = main.get_local_name(b["res"]["value"])
                if local_name not in [cls.test_parent, cls.test_obj]:
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

    def test_instance_name_generates_uuid(self):
        name_1 = main.instance_name(use_uuid=True)
        name_2 = main.instance_name(use_uuid=True)
        self.assertNotEqual(name_1, name_2)
        self.assertTrue(name_1.startswith(self.__class__.test_prefix))
        self.assertEqual(len(name_1), len(self.__class__.test_prefix) + 36)

        seq_name = main.instance_name(use_uuid=False)
        self.assertTrue(seq_name.startswith("instance_"))
        self.assertTrue(len(seq_name) < 20)

    def test_direct_create_instance(self):
        data = {
            "type": "aitken",
            "echo_level": 4,
            "solver": "CFD"
        }
        with patch('main.reload_ontology_from_graphdb') as mock_reload, \
             patch('main.push_to_graphdb') as mock_push:
             
            new_inst = main.create_instance_sparql("convergence_accelerators", self.test_parent, data)
            
            mock_reload.assert_not_called()
            mock_push.assert_not_called()

        self.assertTrue(new_inst.startswith(self.__class__.test_prefix))
        self.assertEqual(len(new_inst), len(self.__class__.test_prefix) + 36)

        new_iri = f"http://coupled_modelling.owl#{new_inst}"
        parent_iri = f"http://coupled_modelling.owl#{self.test_parent}"
        
        res_type = main.query_graphdb(f"""
            ASK {{
                GRAPH <{self.onto_uri}> {{
                    <{new_iri}> a <http://coupled_modelling.owl#convergence_accelerators> .
                }}
            }}
        """)
        self.assertTrue(res_type.get("boolean", False))

        res_link = main.query_graphdb(f"""
            ASK {{
                GRAPH <{self.onto_uri}> {{
                    <{parent_iri}> <http://coupled_modelling.owl#has_convergence_accelerators> <{new_iri}> .
                }}
            }}
        """)
        self.assertTrue(res_link.get("boolean", False))

        res_props = main.query_graphdb(f"""
            SELECT ?p ?o WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <{new_iri}> ?p ?o .
                }}
            }}
        """)
        bindings = res_props.get("results", {}).get("bindings", [])
        properties = {b["p"]["value"]: b["o"]["value"] for b in bindings}
        
        self.assertTrue(properties.get("http://coupled_modelling.owl#has_type", "").startswith("http://coupled_modelling.owl#instance_"))
        self.assertEqual(properties.get("http://coupled_modelling.owl#has_echo_level"), "4")
        self.assertTrue(properties.get("http://coupled_modelling.owl#has_solver", "").startswith("http://coupled_modelling.owl#instance_"))

    def test_create_instance_parent_not_exists(self):
        with self.assertRaises(ValueError) as ctx:
            main.create_instance_sparql("convergence_accelerators", "instance_non_existent_parent_999")
        self.assertIn("does not exist in GraphDB", str(ctx.exception))

    def test_create_instance_ref_exists(self):
        data = {
            "solver": self.test_obj
        }
        new_inst = main.create_instance_sparql("coupling_sequence", self.test_parent, data)
        new_iri = f"http://coupled_modelling.owl#{new_inst}"
        
        res = main.query_graphdb(f"""
            ASK {{
                GRAPH <{self.onto_uri}> {{
                    <{new_iri}> <http://coupled_modelling.owl#has_solver> <http://coupled_modelling.owl#{self.test_obj}> .
                }}
            }}
        """)
        self.assertTrue(res.get("boolean", False))

    def test_create_instance_ref_missing(self):
        data = {
            "solver": "instance_missing_ref_999"
        }
        with self.assertRaises(ValueError) as ctx:
            main.create_instance_sparql("coupling_sequence", self.test_parent, data)
        self.assertIn("does not exist in GraphDB", str(ctx.exception))

    def test_add_value_sparql_creation(self):
        with patch('main.reload_ontology_from_graphdb') as mock_reload, \
             patch('main.push_to_graphdb') as mock_push:
             
            new_inst = main.add_value_sparql(self.test_parent, "convergence_accelerators", None)
            
            mock_reload.assert_not_called()
            mock_push.assert_not_called()

        self.assertTrue(new_inst.startswith(self.__class__.test_prefix))
        new_iri = f"http://coupled_modelling.owl#{new_inst}"
        parent_iri = f"http://coupled_modelling.owl#{self.test_parent}"

        res_type = main.query_graphdb(f"""
            ASK {{
                GRAPH <{self.onto_uri}> {{
                    <{new_iri}> a <http://coupled_modelling.owl#convergence_accelerators> .
                }}
            }}
        """)
        self.assertTrue(res_type.get("boolean", False))

        res_link = main.query_graphdb(f"""
            ASK {{
                GRAPH <{self.onto_uri}> {{
                    <{parent_iri}> <http://coupled_modelling.owl#has_convergence_accelerators> <{new_iri}> .
                }}
            }}
        """)
        self.assertTrue(res_link.get("boolean", False))

    def test_flask_api_create_instance(self):
        client = app.test_client()
        payload = {
            "property": "convergence_accelerators",
            "parent": self.test_parent,
            "data": {
                "type": "aitken",
                "echo_level": 5
            }
        }
        with patch('api.reload_ontology_from_graphdb') as mock_reload, \
             patch('api.save_onto') as mock_save:
             
            res = client.post('/api/v1.0/create_instance/', json=payload)
            self.assertEqual(res.status_code, 201)
            
            new_inst = res.get_json()
            self.assertTrue(new_inst.startswith(self.__class__.test_prefix))
            
            mock_reload.assert_not_called()
            mock_save.assert_not_called()

        new_iri = f"http://coupled_modelling.owl#{new_inst}"
        res_db = main.query_graphdb(f"""
            SELECT ?val WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <{new_iri}> <http://coupled_modelling.owl#has_echo_level> ?val .
                }}
            }}
        """)
        bindings = res_db.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["val"]["value"], "5")

    def test_label_quotes_escaping(self):
        weird_label = 'Weird "Label" \\ with \\ backslashes'
        new_inst = main.create_instance_sparql("solver_settings", self.test_parent, {"label": weird_label})
        new_iri = f"http://coupled_modelling.owl#{new_inst}"
        res = main.query_graphdb(f"""
            SELECT ?lbl WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <{new_iri}> <http://www.w3.org/2000/01/rdf-schema#label> ?lbl .
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["lbl"]["value"], weird_label)

    def test_no_owlready_mutation_during_creation(self):
        with patch("main.get_class") as mock_get_class:
            main.create_instance_sparql("solver_settings", self.test_parent)
            mock_get_class.assert_not_called()

    def test_create_instance_unknown_class(self):
        with self.assertRaises(ValueError) as ctx:
            main.create_instance_sparql("non_existent_class_999", self.test_parent)
        self.assertIn("does not exist in GraphDB", str(ctx.exception))

    def test_api_returns_503_on_graphdb_failure(self):
        client = app.test_client()
        payload = {
            "property": "convergence_accelerators",
            "parent": self.test_parent
        }
        with patch("main.sparql_update", side_effect=GraphDBError("Mock GraphDB failure")):
            res = client.post('/api/v1.0/create_instance/', json=payload)
            self.assertEqual(res.status_code, 503)

    def test_two_creation_calls_do_not_overwrite(self):
        new_inst_1 = main.create_instance_sparql("solver_settings", self.test_parent)
        new_inst_2 = main.create_instance_sparql("solver_settings", self.test_parent)
        
        parent_iri = f"http://coupled_modelling.owl#{self.test_parent}"
        iri_1 = f"http://coupled_modelling.owl#{new_inst_1}"
        iri_2 = f"http://coupled_modelling.owl#{new_inst_2}"
        
        res = main.query_graphdb(f"""
            ASK {{
                GRAPH <{self.onto_uri}> {{
                    <{parent_iri}> <http://coupled_modelling.owl#has_solver_settings> <{iri_1}> .
                    <{parent_iri}> <http://coupled_modelling.owl#has_solver_settings> <{iri_2}> .
                }}
            }}
        """)
        self.assertTrue(res.get("boolean", False))

    def test_class_exists_in_graphdb(self):
        new_inst = main.create_instance_sparql("solver_settings", self.test_parent)
        res = main.query_graphdb(f"""
            ASK {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#solver_settings> a <http://www.w3.org/2002/07/owl#Class> .
                }}
            }}
        """)
        self.assertTrue(res.get("boolean", False))

if __name__ == "__main__":
    unittest.main()
