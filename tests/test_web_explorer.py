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
    get_instance_property_metadata,
    get_class_metadata
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

    @patch('api.get_class_instance_summaries')
    def test_get_class_instance_summaries_optional_class(self, mock_helper):
        """Verify get_class_instance_summaries succeeds with 200 when class param is omitted (global search)."""
        mock_helper.return_value = [{"id": "instance_1", "label": "GlobalInst", "types": ["solver"]}]
        response = self.app.get('/api/v1.0/get_class_instance_summaries/')
        self.assertEqual(response.status_code, 200)
        mock_helper.assert_called_with(None)

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
        def mock_query_responses(query):
            if "SELECT ?inst ?label" in query:
                return {
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
            else:
                return {
                    "results": {
                        "bindings": []
                    }
                }
        mock_query.side_effect = mock_query_responses
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
    @patch('main.validate_class_exists_in_graphdb')
    def test_get_class_instance_summaries_previews(self, mock_val, mock_query):
        """Verify instance summaries include deterministic previews with limits and sorting."""
        def mock_query_responses(query):
            if "SELECT ?inst ?label" in query:
                return {
                    "results": {
                        "bindings": [
                            {
                                "inst": {"value": "http://coupled_modelling.owl#inst_1"}, 
                                "label": {"value": "coupling_system_en", "xml:lang": "en"},
                                "lang": {"value": "en"},
                                "type": {"value": "http://coupled_modelling.owl#coupled_system_1"}
                            }
                        ]
                    }
                }
            else:
                # Outgoing properties for inst_1
                return {
                    "results": {
                        "bindings": [
                            # Exclude type / label properties:
                            {"inst": {"value": "http://coupled_modelling.owl#inst_1"}, "prop": {"value": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"}, "obj": {"type": "uri", "value": "http://coupled_modelling.owl#coupled_system_1"}},
                            {"inst": {"value": "http://coupled_modelling.owl#inst_1"}, "prop": {"value": "http://www.w3.org/2000/01/rdf-schema#label"}, "obj": {"type": "literal", "value": "coupling_system_en"}},
                            
                            # Literals to include:
                            {"inst": {"value": "http://coupled_modelling.owl#inst_1"}, "prop": {"value": "http://coupled_modelling.owl#start_time"}, "obj": {"type": "literal", "value": "0.0", "datatype": "http://www.w3.org/2001/XMLSchema#double"}},
                            {"inst": {"value": "http://coupled_modelling.owl#inst_1"}, "prop": {"value": "http://coupled_modelling.owl#echo_level"}, "obj": {"type": "literal", "value": "2", "datatype": "http://www.w3.org/2001/XMLSchema#integer"}},
                            
                            # Object reference to include (with multiple language labels, testing preferred label preference):
                            {"inst": {"value": "http://coupled_modelling.owl#inst_1"}, "prop": {"value": "http://coupled_modelling.owl#has_solver"}, "obj": {"type": "uri", "value": "http://coupled_modelling.owl#solver_1"}, "obj_label": {"value": "CFD_Solver_fr"}, "obj_lang": {"value": "fr"}},
                            {"inst": {"value": "http://coupled_modelling.owl#inst_1"}, "prop": {"value": "http://coupled_modelling.owl#has_solver"}, "obj": {"type": "uri", "value": "http://coupled_modelling.owl#solver_1"}, "obj_label": {"value": "CFD Solver"}, "obj_lang": {"value": "en"}}
                        ]
                    }
                }
        mock_query.side_effect = mock_query_responses
        res = get_class_instance_summaries("coupled_system")
        
        self.assertEqual(len(res), 1)
        inst = res[0]
        
        # Candidate properties list:
        # echo_level: 2 (literal)
        # start_time: 0.0 (literal)
        # has_solver: CFD Solver (object, with English label preferred)
        
        # Literals are preferred and sorted alphabetically:
        # 1. echo_level (2)
        # 2. start_time (0.0)
        # 3. has_solver (CFD Solver) - object reference falls back at end
        
        self.assertEqual(len(inst["property_preview"]), 3)
        self.assertEqual(inst["property_preview"][0]["property"], "echo_level")
        self.assertEqual(inst["property_preview"][0]["value"], 2)
        self.assertEqual(inst["property_preview"][1]["property"], "start_time")
        self.assertEqual(inst["property_preview"][1]["value"], 0.0)
        self.assertEqual(inst["property_preview"][2]["property"], "solver")
        self.assertEqual(inst["property_preview"][2]["value"], "CFD Solver")
        self.assertEqual(inst["property_preview"][2]["kind"], "object")
        
        # Truncated is False because we fit all 3 candidate properties in the cap of 3
        self.assertFalse(inst["preview_truncated"])

    @patch('main.query_graphdb')
    @patch('main.validate_subject_exists')
    def test_get_instance_property_metadata_parsing(self, mock_val, mock_query):
        """Verify properties aggregation, namespace type filtering, and datatype mappings."""
        def mock_query_responses(query):
            # Batched lookups describing the linked objects (types, preview).
            if "SELECT ?inst ?type" in query:
                return {
                    "results": {
                        "bindings": [
                            {
                                "inst": {"value": "http://coupled_modelling.owl#solver_1"},
                                "type": {"value": "http://coupled_modelling.owl#solver"}
                            }
                        ]
                    }
                }
            if "SELECT ?inst ?prop ?obj" in query:
                return {
                    "results": {
                        "bindings": [
                            {
                                "inst": {"value": "http://coupled_modelling.owl#solver_1"},
                                "prop": {"value": "http://coupled_modelling.owl#has_name"},
                                "obj": {"type": "literal", "value": "CFD", "datatype": "http://www.w3.org/2001/XMLSchema#string"}
                            }
                        ]
                    }
                }
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
        # The linked object is described by its class and a property preview.
        self.assertEqual(res["properties"][2]["values"][0]["types"], ["solver"])
        self.assertEqual(res["properties"][2]["values"][0]["property_preview"], [{"property": "name", "value": "CFD", "kind": "literal"}])
        self.assertFalse(res["properties"][2]["values"][0]["preview_truncated"])

    @patch('api.get_class_metadata')
    def test_get_class_metadata_error_503(self, mock_helper):
        """Verify get_class_metadata returns 503 on GraphDBError."""
        mock_helper.side_effect = GraphDBError("GraphDB offline")
        response = self.app.get('/api/v1.0/get_class_metadata/?class=solver')
        self.assertEqual(response.status_code, 503)

    @patch('api.get_class_metadata')
    def test_get_class_metadata_error_400(self, mock_helper):
        """Verify get_class_metadata returns 400 on ValueError."""
        mock_helper.side_effect = ValueError("Invalid class")
        response = self.app.get('/api/v1.0/get_class_metadata/?class=solver')
        self.assertEqual(response.status_code, 400)

    def test_get_class_metadata_missing_param(self):
        """Verify get_class_metadata returns 400 when class query parameter is missing."""
        response = self.app.get('/api/v1.0/get_class_metadata/')
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data.decode('utf-8'))
        self.assertIn("Missing required query parameter", data["error"])

    @patch('main.query_graphdb')
    @patch('main.validate_class_exists_in_graphdb')
    def test_get_class_metadata_parsing(self, mock_val, mock_query):
        """Verify class metadata parser maps parents, subclasses, equivalent classes, literals, and intersections."""
        def mock_query_responses(query):
            if "owl:Restriction" in query:
                return {
                    "results": {
                        "bindings": [
                            # 1. Qualified restriction: solver_type qualified_cardinality exactly 1
                            {
                                "prop": {"value": "http://coupled_modelling.owl#solver_type"},
                                "prop_label": {"value": "solver_type"},
                                "kind": {"value": "qualified_cardinality"},
                                "cardinality": {"value": "1"},
                                "target": {"value": "http://coupled_modelling.owl#solver_type"},
                                "target_label": {"value": "solver_type"},
                                "target_kind": {"value": "class"}
                            },
                            # 2. Intersection target restriction (member 1)
                            {
                                "prop": {"value": "http://coupled_modelling.owl#has_solver"},
                                "prop_label": {"value": "has_solver"},
                                "kind": {"value": "some_values_from"},
                                "target": {"value": "node123"},
                                "target_kind": {"value": "bnode"},
                                "member": {"value": "http://coupled_modelling.owl#solver"},
                                "member_label": {"value": "solver"}
                            },
                            # 2. Intersection target restriction (member 2)
                            {
                                "prop": {"value": "http://coupled_modelling.owl#has_solver"},
                                "prop_label": {"value": "has_solver"},
                                "kind": {"value": "some_values_from"},
                                "target": {"value": "node123"},
                                "target_kind": {"value": "bnode"},
                                "member": {"value": "http://coupled_modelling.owl#solver_settings"},
                                "member_label": {"value": "solver_settings"}
                            },
                            # 3. Literal target restriction (hasValue boolean)
                            {
                                "prop": {"value": "http://coupled_modelling.owl#print_colors"},
                                "prop_label": {"value": "print_colors"},
                                "kind": {"value": "has_value"},
                                "target": {"value": "true"},
                                "target_kind": {"value": "literal"},
                                "target_datatype": {"value": "http://www.w3.org/2001/XMLSchema#boolean"}
                            }
                        ]
                    }
                }
            elif "rdfs:comment" in query or "skos:definition" in query:
                return {
                    "results": {
                        "bindings": [
                            {"desc": {"value": "Configuration settings for solver wrappers."}}
                        ]
                    }
                }
            elif "rdfs:subClassOf ?parent" in query:
                # Test multilingual label preference: French and English labels
                return {
                    "results": {
                        "bindings": [
                            {
                                "parent": {"value": "http://coupled_modelling.owl#coupling_component"},
                                "parent_label": {"value": "coupling_component_fr"},
                                "lang": {"value": "fr"}
                            },
                            {
                                "parent": {"value": "http://coupled_modelling.owl#coupling_component"},
                                "parent_label": {"value": "Coupling Component"},
                                "lang": {"value": "en"}
                            }
                        ]
                    }
                }
            elif "?sub rdfs:subClassOf" in query:
                return {
                    "results": {
                        "bindings": [
                            {
                                "sub": {"value": "http://coupled_modelling.owl#kratos_solver_wrapper_settings"},
                                "sub_label": {"value": "kratos_solver_wrapper_settings"}
                            }
                        ]
                    }
                }
            elif "owl:equivalentClass" in query:
                # Named equivalent class
                return {
                    "results": {
                        "bindings": [
                            {
                                "eq": {"value": "http://coupled_modelling.owl#wrapper_settings"},
                                "eq_label": {"value": "Wrapper Settings"},
                                "lang": {"value": "en"}
                            }
                        ]
                    }
                }
            return {"results": {"bindings": []}}

        mock_query.side_effect = mock_query_responses
        res = get_class_metadata("solver_wrapper_settings")
        
        self.assertEqual(res["id"], "solver_wrapper_settings")
        self.assertEqual(res["descriptions"], ["Configuration settings for solver wrappers."])
        
        # Superclasses: verifies that English label is preferred over French
        self.assertEqual(len(res["superclasses"]), 1)
        self.assertEqual(res["superclasses"][0]["id"], "coupling_component")
        self.assertEqual(res["superclasses"][0]["label"], "Coupling Component")
        
        # Subclasses
        self.assertEqual(len(res["subclasses"]), 1)
        self.assertEqual(res["subclasses"][0]["id"], "kratos_solver_wrapper_settings")
        
        # Equivalent Classes
        self.assertEqual(len(res["equivalent_classes"]), 1)
        self.assertEqual(res["equivalent_classes"][0]["id"], "wrapper_settings")
        self.assertEqual(res["equivalent_classes"][0]["label"], "Wrapper Settings")
        
        # Asserted Restrictions
        self.assertEqual(len(res["restrictions"]), 3)
        
        # 1. has_solver some_values_from solver & solver_settings (intersection)
        r1 = res["restrictions"][0]
        self.assertEqual(r1["property"]["id"], "has_solver")
        self.assertEqual(r1["kind"], "some_values_from")
        self.assertEqual(r1["target_kind"], "intersection")
        self.assertEqual(r1["target"]["label"], "solver & solver_settings")
        self.assertEqual(len(r1["target"]["members"]), 2)
        self.assertEqual(r1["target"]["members"][0]["id"], "solver")
        self.assertEqual(r1["target"]["members"][1]["id"], "solver_settings")
        
        # 2. print_colors has_value true (literal)
        r2 = res["restrictions"][1]
        self.assertEqual(r2["property"]["id"], "print_colors")
        self.assertEqual(r2["kind"], "has_value")
        self.assertEqual(r2["target_kind"], "literal")
        self.assertEqual(r2["target"]["value"], True)
        self.assertEqual(r2["target"]["datatype"], "http://www.w3.org/2001/XMLSchema#boolean")
        
        # 3. solver_type qualified_cardinality 1 solver_type (class)
        r3 = res["restrictions"][2]
        self.assertEqual(r3["property"]["id"], "solver_type")
        self.assertEqual(r3["kind"], "qualified_cardinality")
        self.assertEqual(r3["cardinality"], 1)
        self.assertEqual(r3["target"]["id"], "solver_type")
        self.assertEqual(r3["target_kind"], "class")


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_search_route_requires_query_text(self):
        """Verify a missing or blank q parameter returns 400."""
        for url in ['/api/v1.0/search/', '/api/v1.0/search/?q=%20']:
            response = self.app.get(url)
            self.assertEqual(response.status_code, 400)

    def test_search_route_rejects_non_integer_limit(self):
        """Verify a non-numeric limit parameter returns 400."""
        response = self.app.get('/api/v1.0/search/?q=x&limit=abc')
        self.assertEqual(response.status_code, 400)

    @patch('api.search_entities')
    def test_search_route_passes_parameters(self, mock_search):
        """Verify q, type, and limit reach search_entities as typed values."""
        mock_search.return_value = {"classes": [], "instances": []}
        response = self.app.get('/api/v1.0/search/?q=mok&type=instance&limit=5')
        self.assertEqual(response.status_code, 200)
        mock_search.assert_called_once_with('mok', 'instance', 5)

    @patch('api.search_entities')
    def test_search_route_defaults_empty_limit(self, mock_search):
        """Verify an empty limit parameter falls back to the default instead of erroring."""
        from main import SEARCH_RESULT_LIMIT
        mock_search.return_value = {"classes": [], "instances": []}
        response = self.app.get('/api/v1.0/search/?q=mok&limit=')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_search.call_args[0][2], SEARCH_RESULT_LIMIT)

    def test_search_rejects_invalid_type_and_limit(self):
        """Verify out-of-contract type, limit, and text values raise ValueError."""
        from main import search_entities
        with self.assertRaises(ValueError):
            search_entities('x', entity_type='bogus')
        with self.assertRaises(ValueError):
            search_entities('x', limit=0)
        with self.assertRaises(ValueError):
            search_entities('x', limit=101)
        with self.assertRaises(ValueError):
            search_entities('   ')
        with self.assertRaises(ValueError):
            search_entities('x' * 201)

    @patch('main.query_graphdb')
    def test_search_classes_only_runs_one_query(self, mock_query):
        """Verify type=class skips the instance query and returns id-only class results."""
        from main import search_entities
        mock_query.return_value = {"results": {"bindings": [{"name": {"value": "coupled_system"}}]}}
        out = search_entities('coup', entity_type='class')
        self.assertEqual(out["classes"], [{"id": "coupled_system"}])
        self.assertEqual(out["instances"], [])
        self.assertEqual(mock_query.call_count, 1)

    @patch('main.query_graphdb')
    def test_search_class_query_matches_names_and_labels(self, mock_query):
        """Verify the class query anchors instances on the project namespace and matches rdfs:label too."""
        from main import search_entities
        mock_query.return_value = {"results": {"bindings": []}}
        search_entities('fluid', entity_type='class')
        sent_query = mock_query.call_args[0][0]
        self.assertIn('rdfs:label', sent_query)
        self.assertNotIn('NamedIndividual', sent_query)

    @patch('main.query_graphdb')
    def test_search_escapes_quotes_in_term(self, mock_query):
        """Verify quotes in the search text are escaped before SPARQL interpolation."""
        from main import search_entities
        mock_query.return_value = {"results": {"bindings": []}}
        search_entities('a"b', entity_type='class')
        sent_query = mock_query.call_args[0][0]
        self.assertIn('a\\"b', sent_query)

    @patch('main.collect_preview_candidates')
    @patch('main.query_graphdb')
    def test_search_instances_use_summary_shape(self, mock_query, mock_candidates):
        """Verify instance results carry the get_class_instance_summaries shape."""
        from main import search_entities
        mock_candidates.return_value = {}
        mock_query.return_value = {"results": {"bindings": [
            {
                "inst": {"value": "http://coupled_modelling.owl#instance_1"},
                "type": {"value": "http://coupled_modelling.owl#coupled_system_1"},
                "label": {"value": "FSI Mok"},
                "lang": {"value": ""}
            }
        ]}}
        out = search_entities('mok', entity_type='instance')
        self.assertEqual(out["classes"], [])
        self.assertEqual(len(out["instances"]), 1)
        summary = out["instances"][0]
        self.assertEqual(summary["id"], "instance_1")
        self.assertEqual(summary["label"], "FSI Mok")
        self.assertEqual(summary["types"], ["coupled_system_1"])
        self.assertEqual(summary["property_preview"], [])
        self.assertFalse(summary["preview_truncated"])

    @patch('main.collect_preview_candidates')
    @patch('main.query_graphdb')
    def test_search_ranks_prefix_matches_first(self, mock_query, mock_candidates):
        """Verify name/label prefix matches come before substring matches regardless of row order."""
        from main import search_entities
        mock_candidates.return_value = {}
        mock_query.return_value = {"results": {"bindings": [
            {
                "inst": {"value": "http://coupled_modelling.owl#instance_1"},
                "type": {"value": "http://coupled_modelling.owl#solvers"},
                "label": {"value": "fsi_mok"},
                "lang": {"value": ""}
            },
            {
                "inst": {"value": "http://coupled_modelling.owl#instance_2"},
                "type": {"value": "http://coupled_modelling.owl#solvers"},
                "label": {"value": "mok_cfd"},
                "lang": {"value": ""}
            }
        ]}}
        out = search_entities('mok', entity_type='instance')
        self.assertEqual([s["label"] for s in out["instances"]], ["mok_cfd", "fsi_mok"])


if __name__ == '__main__':
    unittest.main()
