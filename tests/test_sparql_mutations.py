import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

import unittest
from unittest.mock import patch
import requests
import main
from main import GraphDBError
from api import app

class TestSparqlMutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_subj = "instance_test_m2_subject"
        cls.test_obj = "instance_test_m2_object"
        cls.test_unrelated = "instance_test_unrelated"
        cls.onto_uri = "http://coupled_modelling.owl"
        
        cls.clear_test_resources()

        init_query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        INSERT DATA {{
            GRAPH <{cls.onto_uri}> {{
                <http://coupled_modelling.owl#{cls.test_subj}> rdf:type <http://coupled_modelling.owl#coupled_system> .
                <http://coupled_modelling.owl#{cls.test_subj}> <http://coupled_modelling.owl#has_name> "TestSubject"^^xsd:string .
                
                # Add unrelated annotation metadata (provenance/comment) to verify it is NOT deleted during replace_properties
                <http://coupled_modelling.owl#{cls.test_subj}> <http://www.w3.org/2000/01/rdf-schema#comment> "Provenance metadata"^^xsd:string .
                
                <http://coupled_modelling.owl#{cls.test_obj}> rdf:type <http://coupled_modelling.owl#solver> .
                <http://coupled_modelling.owl#{cls.test_obj}> <http://coupled_modelling.owl#has_name> "TestObject"^^xsd:string .
                
                <http://coupled_modelling.owl#{cls.test_unrelated}> rdf:type <http://coupled_modelling.owl#coupled_system> .
                <http://coupled_modelling.owl#{cls.test_unrelated}> <http://coupled_modelling.owl#has_name> "TestUnrelated"^^xsd:string .
                <http://coupled_modelling.owl#{cls.test_unrelated}> <http://coupled_modelling.owl#has_echo_level> "1"^^xsd:integer .
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
        resources = [cls.test_subj, cls.test_obj, cls.test_unrelated]
        operations = []
        for res in resources:
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
        query = " ; ".join(operations)
        try:
            main.sparql_update(query)
        except Exception:
            pass

    def setUp(self):
        clear_query = f"""
        DELETE {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_subj}> ?p ?o .
            }}
        }}
        WHERE {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_subj}> ?p ?o .
                FILTER(
                    ?p != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> 
                    && ?p != <http://coupled_modelling.owl#has_name>
                    && ?p != <http://www.w3.org/2000/01/rdf-schema#comment>
                )
            }}
        }}
        """
        main.sparql_update(clear_query)

    def test_subject_existence_check(self):
        with self.assertRaises(ValueError) as ctx:
            main.add_value_sparql("instance_non_existent_subject_999", "echo_level", 4)
        self.assertIn("does not exist in GraphDB", str(ctx.exception))

        with self.assertRaises(ValueError):
            main.replace_values_sparql("instance_non_existent_subject_999", {"echo_level": 4})

        with self.assertRaises(ValueError):
            main.add_values_sparql("instance_non_existent_subject_999", {"echo_level": 4})

        with self.assertRaises(ValueError):
            main.replace_properties_sparql("instance_non_existent_subject_999", {"echo_level": 4})

    def test_add_value_literal(self):
        with patch('main.reload_ontology_from_graphdb') as mock_reload, \
             patch('main.push_to_graphdb') as mock_push:
            
            main.add_value_sparql(self.test_subj, "echo_level", 4)
            
            mock_reload.assert_not_called()
            mock_push.assert_not_called()

        res = main.query_graphdb(f"""
            SELECT ?val WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> <http://coupled_modelling.owl#has_echo_level> ?val .
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["val"]["value"], "4")

    def test_add_value_list_literal(self):
        main.add_value_sparql(self.test_subj, "echo_level", [2, 4])
        res = main.query_graphdb(f"""
            SELECT ?val WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> <http://coupled_modelling.owl#has_echo_level> ?val .
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        vals = {b["val"]["value"] for b in bindings}
        self.assertEqual(vals, {"2", "4"})

    def test_add_value_object_reference_exists(self):
        with patch('main.reload_ontology_from_graphdb') as mock_reload, \
             patch('main.push_to_graphdb') as mock_push:
             
            main.add_value_sparql(self.test_subj, "parallel_type", self.test_obj)
            
            mock_reload.assert_not_called()
            mock_push.assert_not_called()

        res = main.query_graphdb(f"""
            SELECT ?val WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> <http://coupled_modelling.owl#has_parallel_type> ?val .
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["val"]["value"], f"http://coupled_modelling.owl#{self.test_obj}")

    def test_add_value_object_reference_missing(self):
        with self.assertRaises(ValueError) as ctx:
            main.add_value_sparql(self.test_subj, "parallel_type", "instance_non_existent_ref")
        self.assertIn("does not exist in GraphDB", str(ctx.exception))

    def test_add_value_creation_supported(self):
        new_inst = main.add_value_sparql(self.test_subj, "solver_settings", None)
        self.assertTrue(new_inst.startswith("instance_"))
        
        new_inst_labeled = main.add_value_sparql(self.test_subj, "solver_settings", "new_unlabelled_instance")
        self.assertTrue(new_inst_labeled.startswith("instance_"))

    def test_delete_value(self):
        main.add_value_sparql(self.test_subj, "print_colors", True)
        
        with patch('main.reload_ontology_from_graphdb') as mock_reload, \
             patch('main.push_to_graphdb') as mock_push:
             
            main.delete_value_sparql(self.test_subj, "print_colors", True)
            
            mock_reload.assert_not_called()
            mock_push.assert_not_called()

        res = main.query_graphdb(f"""
            SELECT ?val WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> <http://coupled_modelling.owl#has_print_colors> ?val .
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 0)

    def test_delete_value_all(self):
        main.add_value_sparql(self.test_subj, "end_time", 1.0)
        main.add_value_sparql(self.test_subj, "end_time", 2.0)
        
        main.delete_value_sparql(self.test_subj, "end_time", None)

        res = main.query_graphdb(f"""
            SELECT ?val WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> <http://coupled_modelling.owl#has_end_time> ?val .
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 0)

    def test_replace_values_empty_list(self):
        main.add_value_sparql(self.test_subj, "start_time", 1.0)
        
        main.replace_values_sparql(self.test_subj, {"start_time": []})

        res = main.query_graphdb(f"""
            SELECT ?val WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> <http://coupled_modelling.owl#has_start_time> ?val .
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 0)

    def test_replace_values_list(self):
        main.add_value_sparql(self.test_subj, "start_time", 0.0)
        
        main.replace_values_sparql(self.test_subj, {"start_time": [1.5, 2.5]})

        res = main.query_graphdb(f"""
            SELECT ?val WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> <http://coupled_modelling.owl#has_start_time> ?val .
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 2)
        vals = {b["val"]["value"] for b in bindings}
        self.assertEqual(vals, {"1.5", "2.5"})

    def test_single_request_batch_add(self):
        data = {
            "echo_level": 5,
            "print_colors": False
        }
        with patch('main.sparql_update', wraps=main.sparql_update) as mock_update:
            main.add_values_sparql(self.test_subj, data)
            mock_update.assert_called_once()

        res = main.query_graphdb(f"""
            SELECT ?p ?o WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> ?p ?o .
                    FILTER(?p = <http://coupled_modelling.owl#has_echo_level> || ?p = <http://coupled_modelling.owl#has_print_colors>)
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 2)

    def test_single_request_batch_delete(self):
        main.add_value_sparql(self.test_subj, "echo_level", 9)
        main.add_value_sparql(self.test_subj, "print_colors", True)
        
        with patch('main.sparql_update', wraps=main.sparql_update) as mock_update:
            main.delete_values_sparql(self.test_subj, ["echo_level", "print_colors"])
            mock_update.assert_called_once()

        res = main.query_graphdb(f"""
            SELECT ?p ?o WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> ?p ?o .
                    FILTER(?p = <http://coupled_modelling.owl#has_echo_level> || ?p = <http://coupled_modelling.owl#has_print_colors>)
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 0)

    def test_replace_properties_preserves_type_and_comment(self):
        main.add_value_sparql(self.test_subj, "echo_level", 1)
        main.add_value_sparql(self.test_subj, "print_colors", True)
        
        data = {
            "start_time": 1.5,
            "end_time": 2.5,
            "label": "New System Label",
            "parallel_type": self.test_obj
        }
        main.replace_properties_sparql(self.test_subj, data)

        res = main.query_graphdb(f"""
            SELECT ?p ?o WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> ?p ?o .
                    FILTER(?p != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>)
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 5)

        properties = {
            binding["p"]["value"]: binding["o"]["value"]
            for binding in bindings
        }
        
        self.assertEqual(properties.get("http://coupled_modelling.owl#has_start_time"), "1.5")
        self.assertEqual(properties.get("http://coupled_modelling.owl#has_end_time"), "2.5")
        self.assertEqual(
            properties.get("http://www.w3.org/2000/01/rdf-schema#label"),
            "New System Label"
        )
        self.assertEqual(
            properties.get("http://coupled_modelling.owl#has_parallel_type"),
            f"http://coupled_modelling.owl#{self.test_obj}"
        )
        self.assertEqual(
            properties.get("http://www.w3.org/2000/01/rdf-schema#comment"),
            "Provenance metadata"
        )

        type_ask = main.query_graphdb(f"""
        ASK {{
            GRAPH <{self.onto_uri}> {{
                <http://coupled_modelling.owl#{self.test_subj}> a <http://coupled_modelling.owl#coupled_system> .
            }}
        }}
        """)
        self.assertTrue(type_ask.get("boolean", False))

    def test_isolation(self):
        main.add_value_sparql(self.test_subj, "echo_level", 7)
        
        res = main.query_graphdb(f"""
            SELECT ?p ?o WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_unrelated}> ?p ?o .
                    FILTER(?p != <http://www.w3.org/1999/02/22-rdf-syntax-ns#type>)
                }}
            }}
        """)
        bindings = res.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 2)
        
        properties = {b["p"]["value"]: b["o"]["value"] for b in bindings}
        self.assertEqual(properties.get("http://coupled_modelling.owl#has_name"), "TestUnrelated")
        self.assertEqual(properties.get("http://coupled_modelling.owl#has_echo_level"), "1")

    def test_flask_api_endpoint(self):
        client = app.test_client()
        payload = {
            "instance": self.test_subj,
            "data": {
                "echo_level": 8,
                "print_colors": True
            }
        }
        
        with patch('api.reload_ontology_from_graphdb') as mock_reload, \
             patch('api.save_onto') as mock_save:
             
            res = client.post('/api/v1.0/replace_values/', json=payload)
            self.assertEqual(res.status_code, 201)
            
            mock_reload.assert_not_called()
            mock_save.assert_not_called()

        res_db = main.query_graphdb(f"""
            SELECT ?val WHERE {{
                GRAPH <{self.onto_uri}> {{
                    <http://coupled_modelling.owl#{self.test_subj}> <http://coupled_modelling.owl#has_echo_level> ?val .
                }}
            }}
        """)
        bindings = res_db.get("results", {}).get("bindings", [])
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["val"]["value"], "8")

    def test_graphdb_failure_returns_503(self):
        client = app.test_client()
        payload = {
            "instance": self.test_subj,
            "data": {"echo_level": 5}
        }
        
        with patch('api.replace_values_sparql', side_effect=GraphDBError("Mocked Connection Failure")):
            res = client.post('/api/v1.0/replace_values/', json=payload)
            self.assertEqual(res.status_code, 503)
            self.assertEqual(res.get_json()["error"], "Mocked Connection Failure")

if __name__ == "__main__":
    unittest.main()
