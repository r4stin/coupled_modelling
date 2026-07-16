import unittest
from unittest.mock import patch, MagicMock
import json
import sys
import os

# Adjust paths to import from backend/
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))

from api import app
from main import (
    GraphDBError, 
    select_preferred_label, 
    get_class_hierarchy_metadata,
    get_class_instance_summaries, 
    get_instance_property_metadata
)


class TestWebExplorer(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_root_index_route(self):
        """Verify root / page returns 200 and includes primary visual panes."""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        
        html_content = response.data.decode('utf-8')
        self.assertIn('id="class-hierarchy"', html_content)
        self.assertIn('id="instance-list"', html_content)
        self.assertIn('id="instance-inspector"', html_content)
        self.assertIn('id="health-badge"', html_content)

    @patch('api.get_graphdb_health')
    def test_health_check_online(self, mock_health):
        """Verify health check returns 200 OK and connected schema on success."""
        mock_health.return_value = {
            "status": "ok",
            "graphdb": "connected",
            "repository": "coupled_modelling"
        }
        
        response = self.app.get('/api/v1.0/health/')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data.decode('utf-8'))
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["graphdb"], "connected")
        self.assertEqual(data["repository"], "coupled_modelling")

    @patch('api.get_graphdb_health')
    def test_health_check_offline(self, mock_health):
        """Verify health check returns 503 Service Unavailable when GraphDB fails."""
        mock_health.side_effect = GraphDBError("Connection refused by GraphDB host")
        
        response = self.app.get('/api/v1.0/health/')
        self.assertEqual(response.status_code, 503)
        
        data = json.loads(response.data.decode('utf-8'))
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["graphdb"], "unavailable")
        self.assertIn("Connection refused", data["error"])

    # --- API Exception response code tests ---

    @patch('api.get_class_hierarchy_metadata')
    def test_get_class_hierarchy_metadata_error_503(self, mock_helper):
        """Verify get_class_hierarchy_metadata returns 503 on GraphDBError."""
        mock_helper.side_effect = GraphDBError("GraphDB down")
        response = self.app.get('/api/v1.0/get_class_hierarchy_metadata/')
        self.assertEqual(response.status_code, 503)

    @patch('api.get_class_hierarchy_metadata')
    def test_get_class_hierarchy_metadata_error_400(self, mock_helper):
        """Verify get_class_hierarchy_metadata returns 400 on ValueError."""
        mock_helper.side_effect = ValueError("Invalid structure")
        response = self.app.get('/api/v1.0/get_class_hierarchy_metadata/')
        self.assertEqual(response.status_code, 400)

    @patch('api.get_class_instance_summaries')
    def test_get_class_instance_summaries_error_503(self, mock_helper):
        """Verify get_class_instance_summaries returns 503 on GraphDBError."""
        mock_helper.side_effect = GraphDBError("GraphDB down")
        response = self.app.get('/api/v1.0/get_class_instance_summaries/?class=coupled_system')
        self.assertEqual(response.status_code, 503)

    @patch('api.get_class_instance_summaries')
    def test_get_class_instance_summaries_error_400(self, mock_helper):
        """Verify get_class_instance_summaries returns 400 on ValueError."""
        mock_helper.side_effect = ValueError("Unknown class")
        response = self.app.get('/api/v1.0/get_class_instance_summaries/?class=coupled_system')
        self.assertEqual(response.status_code, 400)

    @patch('api.get_instance_property_metadata')
    def test_get_instance_property_metadata_error_503(self, mock_helper):
        """Verify get_instance_property_metadata returns 503 on GraphDBError."""
        mock_helper.side_effect = GraphDBError("GraphDB down")
        response = self.app.get('/api/v1.0/get_instance_property_metadata/?instance=instance_cfd')
        self.assertEqual(response.status_code, 503)

    @patch('api.get_instance_property_metadata')
    def test_get_instance_property_metadata_error_400(self, mock_helper):
        """Verify get_instance_property_metadata returns 400 on ValueError."""
        mock_helper.side_effect = ValueError("Unknown instance")
        response = self.app.get('/api/v1.0/get_instance_property_metadata/?instance=instance_cfd')
        self.assertEqual(response.status_code, 400)

    # --- Unit Tests: Label selection logic ---

    def test_select_preferred_label_rules(self):
        """Test English-preferred, untagged-fallback, case-insensitive sorting helper."""
        # Empty inputs fallback
        self.assertEqual(select_preferred_label([], "fallback_id"), "fallback_id")
        
        # English label prioritized over non-English
        labels = [("de", "Kopplung"), ("en", "Coupling")]
        self.assertEqual(select_preferred_label(labels, "fallback"), "Coupling")
        
        # Untagged label prioritized over non-English
        labels = [("fr", "Couplage"), ("", "Coupling_Default")]
        self.assertEqual(select_preferred_label(labels, "fallback"), "Coupling_Default")
        
        # English label prioritized over untagged label
        labels = [("", "Coupling_Default"), ("en", "Coupling")]
        self.assertEqual(select_preferred_label(labels, "fallback"), "Coupling")

        # Lexical case-insensitive sorting tie-breaker
        labels = [("en", "coupling"), ("en", "Coupling_A")]
        self.assertEqual(select_preferred_label(labels, "fallback"), "coupling")

    # --- Unit Tests: SPARQL parser logic tests ---

    @patch('main.query_graphdb')
    def test_get_class_hierarchy_metadata_parsing(self, mock_query):
        """Verify class hierarchy parser outputs root classes and multiple inheritance."""
        mock_query.return_value = {
            "results": {
                "bindings": [
                    {"class": {"value": "http://coupled_modelling.owl#coupled_system"}},
                    {"class": {"value": "http://coupled_modelling.owl#coupled_system_1"}, "parent": {"value": "http://coupled_modelling.owl#coupled_system"}},
                    {"class": {"value": "http://coupled_modelling.owl#coupled_system_1"}, "parent": {"value": "http://coupled_modelling.owl#parallel_system"}}
                ]
            }
        }
        res = get_class_hierarchy_metadata()
        self.assertEqual(len(res), 2)
        
        # Verify alphabetical sorting
        self.assertEqual(res[0]["class"], "coupled_system")
        self.assertEqual(res[0]["parents"], [])
        
        self.assertEqual(res[1]["class"], "coupled_system_1")
        self.assertEqual(res[1]["parents"], ["coupled_system", "parallel_system"])

    @patch('main.query_graphdb')
    @patch('main.validate_class_exists_in_graphdb')
    def test_get_class_instance_summaries_parsing(self, mock_val, mock_query):
        """Verify instance summaries aggregation and label selection parsing."""
        mock_query.return_value = {
            "results": {
                "bindings": [
                    {
                        "inst": {"value": "http://coupled_modelling.owl#inst_1"}, 
                        "label": {"value": "coupling_system_en", "xml:lang": "en"},
                        "lang": {"value": "en"},
                        "type": {"value": "http://coupled_modelling.owl#coupled_system_1"}
                    },
                    {
                        "inst": {"value": "http://coupled_modelling.owl#inst_1"}, 
                        "label": {"value": "coupling_system_de", "xml:lang": "de"},
                        "lang": {"value": "de"},
                        "type": {"value": "http://coupled_modelling.owl#coupled_system_1"}
                    },
                    {
                        "inst": {"value": "http://coupled_modelling.owl#inst_2"},
                        "type": {"value": "http://coupled_modelling.owl#coupled_system_2"}
                    }
                ]
            }
        }
        res = get_class_instance_summaries("coupled_system")
        self.assertEqual(len(res), 2)
        
        # Verify first element is inst_1 resolved to English label and types
        self.assertEqual(res[0]["id"], "inst_1")
        self.assertEqual(res[0]["label"], "coupling_system_en")
        self.assertEqual(res[0]["types"], ["coupled_system_1"])
        
        # Verify second element is inst_2 falling back to ID and types
        self.assertEqual(res[1]["id"], "inst_2")
        self.assertEqual(res[1]["label"], "inst_2")
        self.assertEqual(res[1]["types"], ["coupled_system_2"])

    @patch('main.query_graphdb')
    @patch('main.validate_subject_exists')
    def test_get_instance_property_metadata_parsing(self, mock_val, mock_query):
        """Verify properties aggregation, namespace type filtering, and datatype mappings."""
        def mock_query_responses(query):
            if "rdf:type ?type" in query:
                return {
                    "results": {
                        "bindings": [
                            {
                                "label": {"value": "Instance_Label", "xml:lang": "en"}, 
                                "lang": {"value": "en"},
                                "type": {"value": "http://coupled_modelling.owl#coupled_system"}
                            },
                            {
                                "label": {"value": "Instance_Label", "xml:lang": "en"}, 
                                "lang": {"value": "en"},
                                "type": {"value": "http://www.w3.org/2002/07/owl#NamedIndividual"}
                            }
                        ]
                    }
                }
            else:
                return {
                    "results": {
                        "bindings": [
                            # Literal datatype integer
                            {"prop": {"value": "http://coupled_modelling.owl#has_print_colors"}, "obj": {"type": "literal", "value": "1", "datatype": "http://www.w3.org/2001/XMLSchema#integer"}},
                            # Literal language tag
                            {"prop": {"value": "http://coupled_modelling.owl#has_description"}, "obj": {"type": "literal", "value": "Coupled system desc", "xml:lang": "en"}},
                            # Object reference (multiple duplicate labels aggregated)
                            {
                                "prop": {"value": "http://coupled_modelling.owl#has_solver"}, 
                                "obj": {"type": "uri", "value": "http://coupled_modelling.owl#solver_1"}, 
                                "obj_label": {"value": "CFD_Solver", "xml:lang": "en"},
                                "obj_lang": {"value": "en"}
                            },
                            {
                                "prop": {"value": "http://coupled_modelling.owl#has_solver"}, 
                                "obj": {"type": "uri", "value": "http://coupled_modelling.owl#solver_1"}, 
                                "obj_label": {"value": "CFD_Solver_FR", "xml:lang": "fr"},
                                "obj_lang": {"value": "fr"}
                            }
                        ]
                    }
                }
        
        mock_query.side_effect = mock_query_responses
        res = get_instance_property_metadata("inst_1")
        
        self.assertEqual(res["id"], "inst_1")
        self.assertEqual(res["label"], "Instance_Label")
        self.assertEqual(res["types"], ["coupled_system"])
        
        # Verify properties
        self.assertEqual(len(res["properties"]), 3)
        
        # Verify alphabetical sorting: description, print_colors, solver
        self.assertEqual(res["properties"][0]["property"], "description")
        self.assertEqual(res["properties"][0]["values"][0]["value"], "Coupled system desc")
        self.assertEqual(res["properties"][0]["values"][0]["language"], "en")
        
        self.assertEqual(res["properties"][1]["property"], "print_colors")
        self.assertEqual(res["properties"][1]["values"][0]["value"], 1) # Cast to int
        self.assertEqual(res["properties"][1]["values"][0]["datatype"], "http://www.w3.org/2001/XMLSchema#integer")
        
        self.assertEqual(res["properties"][2]["property"], "solver")
        # Ensure only one object value is generated (labels aggregated)
        self.assertEqual(len(res["properties"][2]["values"]), 1)
        self.assertEqual(res["properties"][2]["values"][0]["kind"], "object")
        self.assertEqual(res["properties"][2]["values"][0]["id"], "solver_1")
        self.assertEqual(res["properties"][2]["values"][0]["label"], "CFD_Solver") # English label preferred


if __name__ == '__main__':
    unittest.main()
