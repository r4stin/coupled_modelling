from owlready2 import *
import types
import os
import requests
import io
import xml.etree.ElementTree as ET
from collections import Counter

GRAPHDB_URL = os.getenv("GRAPHDB_URL", "http://localhost:7200")
REPOSITORY = os.getenv("GRAPHDB_REPOSITORY", "coupled_modelling")
GRAPHDB_USER = os.getenv("GRAPHDB_USER")
GRAPHDB_PASSWORD = os.getenv("GRAPHDB_PASSWORD")


class GraphDBError(RuntimeError):
    """Raised when communication with GraphDB fails."""
    pass


def get_graphdb_auth():
    if GRAPHDB_USER and GRAPHDB_PASSWORD:
        return (GRAPHDB_USER, GRAPHDB_PASSWORD)
    return None


def get_onto_path():
    path = os.path.dirname(os.path.realpath(__file__))
    path = os.path.join(path, 'onto.owl')
    return path


def get_db_path():
    path = os.path.dirname(os.path.realpath(__file__))
    path = os.path.join(path, 'db.sqlite3')
    return path


def get_uri(name):
    if name.startswith('http'):
        return name
    return f"http://coupled_modelling.owl#{name}"


def get_local_name(uri):
    if '#' in uri:
        return uri.split('#')[-1]
    return uri.split('/')[-1]


def query_graphdb(sparql_query):
    """
    Executes a SPARQL query against the GraphDB repository.
    Returns the JSON results as a dictionary.
    """
    url = f"{GRAPHDB_URL}/repositories/{REPOSITORY}"
    headers = {
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/sparql-query"
    }
    try:
        response = requests.post(url, data=sparql_query, headers=headers, auth=get_graphdb_auth())
    except Exception as conn_err:
        raise GraphDBError(f"Connection to GraphDB failed: {conn_err}") from conn_err

    if response.status_code != 200:
        raise GraphDBError(f"GraphDB SPARQL query failed with status code {response.status_code}: {response.text}")
    return response.json()


def sparql_update(sparql_query):
    """
    Executes a SPARQL update statement against the GraphDB repository.
    """
    url = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"
    headers = {
        "Content-Type": "application/sparql-update"
    }
    try:
        response = requests.post(url, data=sparql_query, headers=headers, auth=get_graphdb_auth())
    except Exception as conn_err:
        raise GraphDBError(f"Connection to GraphDB failed: {conn_err}") from conn_err

    if response.status_code not in (200, 204):
        raise GraphDBError(f"SPARQL update failed with status code {response.status_code}: {response.text}")


def validate_local_name(name):
    """Validates that a local name is safe for use in IRIs."""
    if not name or not all(c.isalnum() or c in ('_', '-', '.') for c in name):
        raise ValueError(f"Invalid local name: {name}")


def serialize_iri(local_name):
    """Validates and wraps a local name as a full IRI."""
    validate_local_name(local_name)
    return f"<http://coupled_modelling.owl#{local_name}>"


def serialize_literal(value):
    """Serializes a Python value into a properly typed SPARQL literal."""
    if isinstance(value, bool):
        return f'"{str(value).lower()}"^^xsd:boolean'
    elif isinstance(value, int):
        return f'"{value}"^^xsd:integer'
    elif isinstance(value, float):
        return f'"{value}"^^xsd:double'
    elif isinstance(value, str):
        escaped = (
            value
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"^^xsd:string'
    raise ValueError(f"Unsupported literal type: {type(value)}")


def serialize_object(value):
    """Dispatches to IRI or literal serialization based on type."""
    if isinstance(value, str) and value.startswith("instance"):
        return serialize_iri(value)
    return serialize_literal(value)


def push_to_graphdb():
    """Exports the local ontology and pushes it to GraphDB via REST API replacing the named graph."""
    try:
        temp_path = os.path.join(os.path.dirname(get_onto_path()), "temp_sync.owl")
        try:
            onto.save(temp_path)
            with open(temp_path, "r", encoding="utf-8") as f:
                data_str = f.read()
            
            data = data_str.encode("utf-8")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        url = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"
        headers = {"Content-Type": "application/rdf+xml"}
        params = {"context": f"<{onto_uri}>"}
        response = requests.put(url, data=data, headers=headers, params=params, auth=get_graphdb_auth())
        if response.status_code not in [200, 204]:
            print(f"Failed to push to GraphDB: {response.status_code} - {response.text}")
        else:
            print("Successfully synchronized local ontology with GraphDB (named graph).")
            # Note: GraphDB/RDF4J normalizes empty-path base URIs to include a trailing slash (RFC 3986).
            # Because Owlready2 saves using relative `rdf:about="#entity"` references, the GraphDB parser
            # resolves them to `http://coupled_modelling.owl/#entity`. 
            # We run a SPARQL update here to clean and restore them to the canonical hash namespace (`...#entity`).
            try:
                update_url = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"
                update_headers = {"Content-Type": "application/sparql-update"}
                update_query = f"""
                DELETE {{
                    GRAPH <{onto_uri}> {{
                        ?s ?p ?o .
                    }}
                }}
                INSERT {{
                    GRAPH <{onto_uri}> {{
                        ?s2 ?p2 ?o2 .
                    }}
                }}
                WHERE {{
                    GRAPH <{onto_uri}> {{
                        ?s ?p ?o .
                        BIND(IF(isIRI(?s),
                            IRI(REPLACE(STR(?s), "^http://coupled_modelling\\\\.owl/#", "http://coupled_modelling.owl#")),
                            ?s
                        ) AS ?s2)
                        BIND(IF(isIRI(?p),
                            IRI(REPLACE(STR(?p), "^http://coupled_modelling\\\\.owl/#", "http://coupled_modelling.owl#")),
                            ?p
                        ) AS ?p2)
                        BIND(IF(isIRI(?o),
                            IRI(REPLACE(STR(?o), "^http://coupled_modelling\\\\.owl/#", "http://coupled_modelling.owl#")),
                            ?o
                        ) AS ?o2)
                        FILTER(?s != ?s2 || ?p != ?p2 || ?o != ?o2)
                    }}
                }}
                """
                update_res = requests.post(update_url, data=update_query, headers=update_headers, auth=get_graphdb_auth())
                if update_res.status_code not in [200, 204]:
                    print(f"Failed to run GraphDB namespace rewrite: {update_res.status_code} - {update_res.text}")
                else:
                    print("Successfully rewrote GraphDB namespaces (removed trailing slashes).")
            except Exception as rewrite_err:
                print(f"Failed to rewrite GraphDB namespaces: {rewrite_err}")
    except Exception as e:
        print(f"Failed to push to GraphDB: {e}")


def pull_from_graphdb():
    """Fetches ontology from GraphDB named graph directly."""
    url = f"{GRAPHDB_URL}/repositories/{REPOSITORY}/statements"
    headers = {"Accept": "application/rdf+xml"}
    params = {"context": f"<{onto_uri}>", "infer": "false"}
    try:
        response = requests.get(url, headers=headers, params=params, auth=get_graphdb_auth())
        if response.status_code == 200:
            content = response.content
            if b"rdf:about" in content or b"rdf:Description" in content:
                # Validate XML
                try:
                    ET.fromstring(content)
                    return content
                except Exception as xml_err:
                    print(f"Invalid RDF/XML retrieved from GraphDB: {xml_err}")
                    return None
        return None
    except Exception as e:
        print(f"Could not pull from GraphDB: {e}")
        return None


def reload_ontology_from_graphdb():
    global onto, default_world
    try:
        import owlready2
        owlready2.default_world = owlready2.World()
        default_world = owlready2.default_world
        onto = load_onto()
    except Exception as e:
        print(f"Failed to load latest ontology from GraphDB: {e}")


def new_onto():
    onto = default_world.get_ontology(onto_uri)
    return onto


def load_onto():
    """
    Loads an ontology.

    Returns:
        Loaded ontology
    """ 
    rdf_xml_data = None
    try:
        rdf_xml_data = pull_from_graphdb()
    except Exception as e:
        print(f"Failed to pull from GraphDB during load: {e}")

    onto = default_world.get_ontology(onto_uri)

    if rdf_xml_data:
        try:
            onto.load(fileobj=io.BytesIO(rdf_xml_data))
            print("Successfully loaded ontology from GraphDB.")
            return onto
        except Exception as e:
            print(f"Failed to load pulled RDF/XML into Owlready2: {e}. Falling back to local onto.owl.")

    try:
        with open(get_onto_path(), "rb") as f:
            onto.load(fileobj=f)
        print("Successfully loaded ontology from local onto.owl.")
        return onto
    except Exception as e:
        print(f"Failed to load local onto.owl: {e}")
        onto.load()
        return onto


def save_onto():
    """
    Saves the ontology.

    """
    try:
        push_to_graphdb()
    except Exception as e:
        print(f"Failed to push to GraphDB during save: {e}")


def save_locally():
    """
    Saves the ontology into a file.

    """
    onto.save(get_onto_path())


def get_class(name):
    """
    Gets or creates an OWL-class with a given name, which is used as the class URI and its label.

    Args:
        name (str): Name of the class.
    """
    with onto:
        cl = onto.search_one(label = name)
        if not cl:
            cl = types.new_class(name, (Thing,))
            cl.label = name
        return cl


def get_relation(name, functional = False):
    """
    Gets or creates an ObjectProperty with a given name.

    Args:
        name (str): Name of the ObjectProperty.
        functional (bool, optional): if the ObjectProperty is functional.
    """
    #if name == 'data':
    #    name = 'data_'
    name = f'has_{name}'
    with onto:
        rel = onto.search_one(label = name)
        if not rel:
            if functional:
                rel = types.new_class(name, (ObjectProperty, FunctionalProperty))
            else:
                rel = types.new_class(name, (ObjectProperty,))
            rel.label = name
        return rel


def get_property(name, functional = False):
    """
    Gets or creates a DataProperty with a given name.

    Args:
        name (str): Name of the DataProperty.
        functional (bool, optional): if the DataProperty is functional.
    """
    name = f'has_{name}'
    with onto:
        prop = onto.search_one(label = name)
        if not prop:
            if functional:
                prop = types.new_class(name, (DataProperty, FunctionalProperty))
            else:
                prop = types.new_class(name, (DataProperty,))
            prop.label = name
        return prop


def instance_name(use_uuid=True):
    if use_uuid:
        import uuid
        return f"instance_{uuid.uuid4()}"
    n = len(list(onto.individuals())) + 1
    return f'instance_{n}'


def has_only_label(inst):
    props = list(inst.get_properties())
    props = [x.name for x in props]
    return props == ['label']


def dict_to_inst(inst, pred_name, data, functional=False):
    obj_cl = get_class(pred_name)
    rel = get_relation(pred_name, functional)
    obj_inst = obj_cl(instance_name(use_uuid=False))
    for inst_pred_name, inst_obj_data in data.items():
        obj_inst = add_coupled_system(obj_inst, inst_pred_name, inst_obj_data)
        if obj_inst not in rel[inst]:
            print('dict', inst, rel, obj_inst)
            rel[inst].append(obj_inst)


def str_to_inst(inst, pred_name, label, functional=False):
    obj_cl = get_class(pred_name)
    rel = get_relation(pred_name, functional)
    res = onto.search(label = label)
    obj_inst = None
    for item in res:
        if has_only_label(item):
            obj_inst = item
            break
    if obj_inst:
        if not obj_cl in obj_inst.is_a:
            obj_inst.is_a.append(obj_cl)
    else:
        obj_inst = obj_cl(instance_name(use_uuid=False))
        obj_inst.label = [label]
    if obj_inst not in rel[inst]:
        print('str', inst, rel, obj_inst)
        rel[inst].append(obj_inst)


def num_to_literal(inst, pred_name, num, functional=False):
    prop = get_property(pred_name, functional)
    if num not in prop[inst]:
        print('num', inst, prop, num)
        prop[inst].append(num)


def add_coupled_system(inst, pred_name, obj_data):
    """
    Creates a coupled system with given data.

    Args:
        inst (OWL instance): OWL-instance.
        pred_name (str): A property name from the data.
        obj_data: Value of the property from the data.
    """
    with onto:
        if type(obj_data) == dict and all([type(obj_value) == dict for obj_key, obj_value in obj_data.items()]):
            rel = get_relation(pred_name)
            for obj_key, obj_value in obj_data.items():
                obj_cl = get_class(pred_name)
                #obj_inst = onto.search_one(label = obj_key)
                #if obj_inst:
                #    if not obj_cl in obj_inst.is_a:
                #        obj_inst.is_a.append(obj_cl)
                #else:
                obj_inst = obj_cl(instance_name(use_uuid=False))
                obj_inst.label = obj_key
                for inst_pred_name, inst_obj_data in obj_value.items():
                    obj_inst = add_coupled_system(obj_inst, inst_pred_name, inst_obj_data)
                    if obj_inst not in rel[inst]:
                        print('dict_dict', inst, rel, obj_inst)
                        rel[inst].append(obj_inst)
        elif type(obj_data) == dict:
            dict_to_inst(inst, pred_name, obj_data)
        elif type(obj_data) == list:
            for i, obj_item in enumerate(obj_data):
                if type(obj_item) == dict:
                    dict_to_inst(inst, pred_name, obj_item)
                elif type(obj_item) == str:
                    str_to_inst(inst, pred_name, obj_item)
                else:
                    num_to_literal(inst, pred_name, obj_item)
        elif type(obj_data) == str:
            str_to_inst(inst, pred_name, obj_data)
        else:
            num_to_literal(inst, pred_name, obj_data, True)

    return inst


def create_coupled(label):
    """
    Creates an OWL-instance of the coupled system class with a given label.

    Args:
        label (str): Label for the coupled system.

    Returns:
        An OWL instance for the coupled system
    """
    with onto:
        coupled_system = get_class('coupled_system')
        inst = coupled_system(instance_name(use_uuid=False))
        inst.label = label
    return inst.name


def get_class_properties(class_name):
    """
    For a given class, returns a dictionary of its axioms.

    Args:
        class_name (str): Class name.

    Returns:
        The dictionary of the class axioms.
    """
    cl = onto[class_name]
    props = []
    for restr in cl.is_a:
        if hasattr(restr, 'property'):
            value = restr.value
            if hasattr(value, 'Classes'):
                props.append({
                    'property': restr.property.name,
                    'cardinality': restr.cardinality,
                    'value': [x.name for x in value.Classes]})
            else:
                props.append({
                    'property': restr.property.name,
                    'cardinality': restr.cardinality,
                    'value': value.__name__})
    #props.pop('label', None)
    return props


def get_class_properties_recursively(class_name, depth=1, recursive=False):
    """
    For a given class, returns a dictionary of its axioms of the specified depth.

    Args:
        class_name (str): Class name.
        depth (int, optional): Depth of the recursion.
        recursive (bool, optional): If True, the depth of recursion is unlimited.

    Returns:
        The dictionary of the class axioms.
    """
    props = get_class_properties(class_name)
    
    if recursive:
        depth = None
    
    if depth:
        depth -= 1
    
    print(depth)
    print(recursive)

    if depth == None or depth > 0:
        for i, item in enumerate(props):
            if type(item['value']) == list:
                temp_list = []
                for value in item['value']:
                    temp_list.append({value: get_class_properties_recursively(value, depth, recursive)})
                    props[i]['value'] = temp_list
    return props


def get_subclasses(class_label):
    """
    For a given class, returns its subclasses.

    Args:
        class_label (str): Class label.

    Returns:
        A list of the subclass names.
    """
    try:
        query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?subClass WHERE {{
            GRAPH <{onto_uri}> {{
                ?class rdfs:label "{class_label}" .
                ?subClass rdfs:subClassOf ?class .
                FILTER (?subClass != ?class)
            }}
        }}
        """
        res = query_graphdb(query)
        subclasses = []
        for binding in res.get("results", {}).get("bindings", []):
            subclass_uri = binding["subClass"]["value"]
            subclasses.append(get_local_name(subclass_uri))
        return subclasses
    except Exception as e:
        print(f"GraphDB query failed in get_subclasses: {e}. Falling back to Owlready2.")
        cl = onto.search_one(label = class_label)
        if cl:
            return [x.name for x in cl.subclasses()]
        return []


def get_instance_properties(inst_name):
    """
    For a given instance, returns its statements.

    Args:
        inst_name (str): Instance name.

    Returns:
        A dictionary of instance properties and their values.
    """
    try:
        inst_uri = get_uri(inst_name)
        query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?prop ?obj ?obj_label (COUNT(?other_prop) AS ?prop_count) WHERE {{
            GRAPH <{onto_uri}> {{
                <{inst_uri}> ?prop ?obj .
                FILTER (?prop != rdf:type)
                OPTIONAL {{
                    ?obj rdfs:label ?obj_label .
                }}
                OPTIONAL {{
                    ?obj ?other_prop ?other_val .
                    FILTER (?other_prop != rdf:type && ?other_prop != rdfs:label)
                }}
            }}
        }} GROUP BY ?prop ?obj ?obj_label
        """
        res = query_graphdb(query)
        
        raw_props = {}
        for binding in res.get("results", {}).get("bindings", []):
            prop_uri = binding["prop"]["value"]
            prop_name = get_local_name(prop_uri).replace('has_', '')
            
            obj_binding = binding["obj"]
            obj_type = obj_binding.get("type")
            obj_val = obj_binding["value"]
            
            if obj_type in ["literal", "typed-literal"]:
                datatype = obj_binding.get("datatype")
                if datatype == "http://www.w3.org/2001/XMLSchema#integer":
                    val = int(obj_val)
                elif datatype == "http://www.w3.org/2001/XMLSchema#double" or datatype == "http://www.w3.org/2001/XMLSchema#float":
                    val = float(obj_val)
                elif datatype == "http://www.w3.org/2001/XMLSchema#boolean":
                    val = obj_val.lower() == "true"
                else:
                    if obj_val == "True":
                        val = True
                    elif obj_val == "False":
                        val = False
                    else:
                        try:
                            if '.' in obj_val:
                                val = float(obj_val)
                            else:
                                val = int(obj_val)
                        except ValueError:
                            val = obj_val
            else:
                prop_count = int(binding.get("prop_count", {}).get("value", 0))
                if prop_count == 0 and "obj_label" in binding:
                    val = binding["obj_label"]["value"]
                else:
                    val = get_local_name(obj_val)
            
            if prop_name not in raw_props:
                raw_props[prop_name] = []
            if val not in raw_props[prop_name]:
                raw_props[prop_name].append(val)
                
        props = {}
        for prop_name, temp in raw_props.items():
            if len(temp) == 1 and not prop_name in force_list():
                props[prop_name] = temp[0]
            else:
                props[prop_name] = temp
        return props
    except Exception as e:
        print(f"GraphDB query failed in get_instance_properties: {e}. Falling back to Owlready2.")
        inst = onto[inst_name]
        props = {}
        for prop in inst.get_properties():
            temp = []
            for obj in prop[inst]:
                if hasattr(obj, 'name'):
                    if has_only_label(obj):
                        temp.append(obj.label[0])
                    else:
                        temp.append(obj.name)
                else:
                    temp.append(obj)
            prop_name = prop.name.replace('has_', '')
            if len(temp) == 1 and not prop_name in force_list():
                props[prop_name] = temp[0]
            else:
                props[prop_name] = temp
        return props

    
def get_class_instances(class_name):
    """
    For a given class, returns its instances.

    Args:
        class_name (str): Name of the class.

    Returns:
        A list of class instance names.
    """
    try:
        class_uri = get_uri(class_name)
        query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?inst WHERE {{
            GRAPH <{onto_uri}> {{
                ?inst rdf:type/rdfs:subClassOf* <{class_uri}> .
            }}
        }}
        """
        res = query_graphdb(query)
        instances = []
        for binding in res.get("results", {}).get("bindings", []):
            inst_uri = binding["inst"]["value"]
            instances.append(get_local_name(inst_uri))
        return instances
    except Exception as e:
        print(f"GraphDB query failed in get_class_instances: {e}. Falling back to Owlready2.")
        cl = onto[class_name]
        if cl:
            return [x.name for x in cl.instances()]
        return []


def get_values(subj, prop):
    """
    Returns a property for the given subject .

    Args:
        subj (str): A name of the instance that is the subject of the statement.
        prop (str): Label of the property.

    Returns:
        The value.
    """
    subj = onto[subj]
    prop = onto[f'has_{prop}']
    values = prop[subj]
    res = []
    for value in values:
        if hasattr(value, 'name'):
            res.append(value.name)
        else:
            res.append(value)
    return res

    
def serialize_subject(subj):
    if isinstance(subj, str) and (subj.startswith("http://") or subj.startswith("https://")):
        if any(char in subj for char in '<>"\' {}^`\n\r\t'):
            raise ValueError(f"Invalid characters in subject URI: {subj}")
        return f"<{subj}>"
    if hasattr(subj, "name"):
        return serialize_iri(subj.name)
    return serialize_iri(subj)


def get_property_iri(prop_name):
    if prop_name == 'label':
        return "<http://www.w3.org/2000/01/rdf-schema#label>"
    return serialize_iri(f"has_{prop_name}")


def instance_exists(name):
    instance_iri = serialize_iri(name)
    query = f"""
    ASK {{
        GRAPH <http://coupled_modelling.owl> {{
            {instance_iri} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?type .
        }}
    }}
    """
    res = query_graphdb(query)
    return res.get("boolean", False)


def validate_subject_exists(subj):
    subj_iri = serialize_subject(subj)
    query = f"""
    ASK {{
        GRAPH <http://coupled_modelling.owl> {{
            {subj_iri} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> ?type .
        }}
    }}
    """
    res = query_graphdb(query)
    if not res.get("boolean", False):
        raise ValueError(f"Subject instance {subj} does not exist in GraphDB.")


def validate_class_exists_in_graphdb(class_name):
    class_iri = serialize_iri(class_name)
    query = f"""
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    ASK {{
        GRAPH <http://coupled_modelling.owl> {{
            {class_iri} a owl:Class .
        }}
    }}
    """
    res = query_graphdb(query)
    if not res.get("boolean", False):
        raise ValueError(f"Class {class_name} does not exist in GraphDB.")


def is_object_property_in_graphdb(prop_name):
    try:
        prop_iri = serialize_iri(f"has_{prop_name}")
        class_iri = serialize_iri(prop_name)
    except ValueError:
        return False
        
    query = f"""
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    ASK {{
        GRAPH <http://coupled_modelling.owl> {{
            {{ {prop_iri} a owl:ObjectProperty . }}
            UNION
            {{ {class_iri} a owl:Class . }}
        }}
    }}
    """
    res = query_graphdb(query)
    return res.get("boolean", False)


def resolve_instance_by_label(class_label, label):
    validate_class_exists_in_graphdb(class_label)
    class_iri = serialize_iri(class_label)
    label_literal = serialize_literal(label)
    query = f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    SELECT ?inst WHERE {{
        GRAPH <http://coupled_modelling.owl> {{
            ?inst rdf:type {class_iri} .
            ?inst rdfs:label {label_literal} .
        }}
    }}
    LIMIT 1
    """
    res = query_graphdb(query)
    bindings = res.get("results", {}).get("bindings", [])
    if bindings:
        inst_iri = bindings[0]["inst"]["value"]
        return get_local_name(inst_iri)
    return None


def resolve_or_create_instance_by_label(class_label, label):
    existing = resolve_instance_by_label(class_label, label)
    if existing:
        return existing
        
    validate_class_exists_in_graphdb(class_label)
    class_iri = serialize_iri(class_label)
    label_literal = serialize_literal(label)
    new_ref_name = instance_name(use_uuid=True)
    new_ref_iri = serialize_iri(new_ref_name)
    
    create_query = f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    INSERT DATA {{
        GRAPH <http://coupled_modelling.owl> {{
            {new_ref_iri} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> {class_iri} .
            {new_ref_iri} rdfs:label {label_literal} .
        }}
    }}
    """
    sparql_update(create_query)
    return new_ref_name


def resolve_val_sparql(prop_name, val):
    if val is None:
        return None
    if isinstance(val, str) and not val.startswith("instance") and prop_name != "label":
        if is_object_property_in_graphdb(prop_name):
            return resolve_or_create_instance_by_label(prop_name, val)
    return val


# --- Owlready2 Mutation Helpers ---
# Used by ontology construction, inference, creation, and copy workflows
def add_value(subj, prop_name, value=None):
    """
    Adds a value to the given subject and property.

    Args:
        subj (str): A name of the instance that is the subject of the statement.
        prop (str): Label of the property.
        value (optional): value to add. If None, a new instance is created.

    Returns:
        The value, useful if the new instance is created.
    """
    subj = onto[subj]
    if prop_name == 'label':
        subj.label = value
        return value

    if hasattr(value, 'name'):
        value = onto[value]
    
    if value == None:
        cl = get_class(prop_name)
        with onto:
            value = cl(instance_name(use_uuid=False))
        prop = get_relation(prop_name)
        prop[subj].append(value)
    elif type(value) == str and not value.startswith('http'):
        if value.startswith('instance'):
            prop = get_relation(prop_name)
            prop[subj].append(value)
        else:
            value = str_to_inst(subj, prop_name, value)
    else:
        prop = get_property(prop_name)
        prop[subj].append(value)
    if hasattr(value, 'name'):
        return value.name


def delete_value(subj, prop, value=None):
    """
    Deletes a value from the given subject and property.

    Args:
        subj (str): A name of the instance that is the subject of the statement.
        prop (str): Label of the property.
        value (optional): value to delete. If not specified, all values are removed.
    """
    subj = onto[subj]
    if value and hasattr(value, 'name'):
        value = onto[value]
    
    if prop == 'label':
        subj.label = []
        return
    
    prop = onto[f'has_{prop}']
    if value:
        prop[subj].remove(value)
    else:
        prop[subj] = []            


def replace_values(subj, data):
    """
    Replaces all values of the property with the specified new value for each key-value pair in the provided dictionary.

    Args:
        subj (str): A name of the instance properties of which to replace.
        data (dict): A dictionary of property-value pairs
    """
    for prop, value in data.items():
        delete_value(subj, prop)
        add_value(subj, prop, value)


def delete_values(inst, props):
    for prop in props:
        delete_value(inst, prop)


def add_values(inst, data):
    for prop, value in data.items():
        add_value(inst, prop, value)


def replace_properties(inst_name, data):
    inst = onto[inst_name]
    props = inst.get_properties()
    for prop in props:
        prop = prop.name.replace('has_', '')
        delete_value(inst_name, prop)
    for prop, value in data.items():
        add_value(inst_name, prop, value)


# --- New Direct SPARQL Mutation Helpers ---

def add_value_sparql(subj, prop_name, value=None):
    validate_subject_exists(subj)
    
    if value is None:
        validate_class_exists_in_graphdb(prop_name)
        new_inst_name = instance_name(use_uuid=True)
        new_inst_iri = serialize_iri(new_inst_name)
        class_iri = serialize_iri(prop_name)
        
        subj_iri = serialize_subject(subj)
        pred_iri = get_property_iri(prop_name)
        
        query = f"""
        INSERT DATA {{
            GRAPH <http://coupled_modelling.owl> {{
                {new_inst_iri} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> {class_iri} .
                {subj_iri} {pred_iri} {new_inst_iri} .
            }}
        }}
        """
        sparql_update(query)
        return new_inst_name

    values = value if isinstance(value, list) else [value]
    resolved_values = [resolve_val_sparql(prop_name, val) for val in values]
    
    # Validate each item
    for val in resolved_values:
        if val is None or (isinstance(val, str) and not val.startswith("instance") and prop_name != "label"):
            if is_object_property_in_graphdb(prop_name):
                raise ValueError("Creation of new individuals via direct SPARQL mutations is not supported in Milestone 2/3 except through explicit creation APIs.")
        if isinstance(val, str) and val.startswith("instance") and not instance_exists(val):
            raise ValueError(f"Referenced instance {val} does not exist in GraphDB.")
            
    subj_iri = serialize_subject(subj)
    pred_iri = get_property_iri(prop_name)
    
    triples = []
    for val in resolved_values:
        if val is not None:
            obj_val = serialize_object(val)
            triples.append(f"{subj_iri} {pred_iri} {obj_val} .")
            
    if triples:
        query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        INSERT DATA {{
            GRAPH <http://coupled_modelling.owl> {{
                {" ".join(triples)}
            }}
        }}
        """
        sparql_update(query)
    return resolved_values if isinstance(value, list) else resolved_values[0]


def delete_value_sparql(subj, prop_name, value=None):
    # Idempotent delete on subject: no error raised if subject doesn't exist
    subj_iri = serialize_subject(subj)
    pred_iri = get_property_iri(prop_name)
    
    if value is not None:
        values = value if isinstance(value, list) else [value]
        triples = []
        for val in values:
            obj_val = serialize_object(val)
            triples.append(f"{subj_iri} {pred_iri} {obj_val} .")
        if triples:
            query = f"""
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            DELETE DATA {{
                GRAPH <http://coupled_modelling.owl> {{
                    {" ".join(triples)}
                }}
            }}
            """
            sparql_update(query)
    else:
        query = f"""
        DELETE WHERE {{
            GRAPH <http://coupled_modelling.owl> {{
                {subj_iri} {pred_iri} ?old_val .
            }}
        }}
        """
        sparql_update(query)


def replace_values_sparql(subj, data):
    """
    Replaces all values of the property with the specified new value for each key-value pair in data.
    
    Note: Direct implicit creation is currently supported through add_value_sparql() 
    and create_instance_sparql(), not this batch replacement API.
    """
    validate_subject_exists(subj)
    
    # Upfront validation for all properties
    for prop_name, value in data.items():
        values = value if isinstance(value, list) else [value]
        for val in values:
            if val is None or (isinstance(val, str) and not val.startswith("instance") and prop_name != "label"):
                raise ValueError("Creation of new individuals via direct SPARQL mutations is not supported in Milestone 2/3 except through explicit creation APIs.")
            if isinstance(val, str) and val.startswith("instance") and not instance_exists(val):
                raise ValueError(f"Referenced instance {val} does not exist in GraphDB.")
                
    subj_iri = serialize_subject(subj)
    delete_triples = []
    insert_triples = []
    where_clauses = []
    
    for idx, (prop_name, value) in enumerate(data.items()):
        pred_iri = get_property_iri(prop_name)
        values = value if isinstance(value, list) else [value]
        
        var_name = f"old_{idx}"
        delete_triples.append(f"{subj_iri} {pred_iri} ?{var_name} .")
        where_clauses.append(f"OPTIONAL {{ {subj_iri} {pred_iri} ?{var_name} . }}")
        
        for val in values:
            if val is not None:
                obj_val = serialize_object(val)
                insert_triples.append(f"{subj_iri} {pred_iri} {obj_val} .")
                
    if insert_triples:
        query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        DELETE {{
            GRAPH <http://coupled_modelling.owl> {{
                {" ".join(delete_triples)}
            }}
        }}
        INSERT {{
            GRAPH <http://coupled_modelling.owl> {{
                {" ".join(insert_triples)}
            }}
        }}
        WHERE {{
            GRAPH <http://coupled_modelling.owl> {{
                {" ".join(where_clauses)}
            }}
        }}
        """
    else:
        query = f"""
        DELETE {{
            GRAPH <http://coupled_modelling.owl> {{
                {" ".join(delete_triples)}
            }}
        }}
        WHERE {{
            GRAPH <http://coupled_modelling.owl> {{
                {" ".join(where_clauses)}
            }}
        }}
        """
    sparql_update(query)


def delete_values_sparql(inst, props):
    # Idempotent delete on subject: no error raised if subject doesn't exist
    subj_iri = serialize_subject(inst)
    operations = []
    
    for idx, prop_name in enumerate(props):
        pred_iri = get_property_iri(prop_name)
        operations.append(f"""
        DELETE WHERE {{
            GRAPH <http://coupled_modelling.owl> {{
                {subj_iri} {pred_iri} ?old_{idx} .
            }}
        }}
        """)
        
    query = " ; ".join(operations)
    sparql_update(query)


def add_values_sparql(inst, data):
    """
    Adds values to the given subject instance from a dictionary of property-value pairs.
    
    Note: Direct implicit creation is currently supported through add_value_sparql() 
    and create_instance_sparql(), not this batch replacement API.
    """
    validate_subject_exists(inst)
    
    # Upfront validation for all properties
    for prop_name, value in data.items():
        values = value if isinstance(value, list) else [value]
        for val in values:
            if val is None or (isinstance(val, str) and not val.startswith("instance") and prop_name != "label"):
                raise ValueError("Creation of new individuals via direct SPARQL mutations is not supported in Milestone 2/3 except through explicit creation APIs.")
            if isinstance(val, str) and val.startswith("instance") and not instance_exists(val):
                raise ValueError(f"Referenced instance {val} does not exist in GraphDB.")
                
    subj_iri = serialize_subject(inst)
    triples = []
    
    for prop_name, value in data.items():
        pred_iri = get_property_iri(prop_name)
        values = value if isinstance(value, list) else [value]
        for val in values:
            if val is not None:
                obj_val = serialize_object(val)
                triples.append(f"{subj_iri} {pred_iri} {obj_val} .")
        
    if triples:
        query = f"""
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        INSERT DATA {{
            GRAPH <http://coupled_modelling.owl> {{
                {" ".join(triples)}
            }}
        }}
        """
        sparql_update(query)


def replace_properties_sparql(inst_name, data):
    """
    Replaces properties of the given instance.
    
    Note: Direct implicit creation is currently supported through add_value_sparql() 
    and create_instance_sparql(), not this batch replacement API.
    """
    validate_subject_exists(inst_name)
    
    # Upfront validation for all properties
    for prop_name, value in data.items():
        values = value if isinstance(value, list) else [value]
        for val in values:
            if val is None or (isinstance(val, str) and not val.startswith("instance") and prop_name != "label"):
                raise ValueError("Creation of new individuals via direct SPARQL mutations is not supported in Milestone 2/3 except through explicit creation APIs.")
            if isinstance(val, str) and val.startswith("instance") and not instance_exists(val):
                raise ValueError(f"Referenced instance {val} does not exist in GraphDB.")
                
    subj_iri = serialize_subject(inst_name)
    insert_triples = []
    
    for prop_name, value in data.items():
        pred_iri = get_property_iri(prop_name)
        values = value if isinstance(value, list) else [value]
        for val in values:
            if val is not None:
                obj_val = serialize_object(val)
                insert_triples.append(f"{subj_iri} {pred_iri} {obj_val} .")
        
    query = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    DELETE {{
        GRAPH <http://coupled_modelling.owl> {{
            {subj_iri} ?p ?o .
        }}
    }}
    WHERE {{
        GRAPH <http://coupled_modelling.owl> {{
            {subj_iri} ?p ?o .
            FILTER(
                STRSTARTS(STR(?p), "http://coupled_modelling.owl#has_")
                || ?p = rdfs:label
            )
        }}
    }}
    """
    if insert_triples:
        query += f""" ;
        INSERT DATA {{
            GRAPH <http://coupled_modelling.owl> {{
                {" ".join(insert_triples)}
            }}
        }}
        """
    sparql_update(query)


def create_instance_sparql(prop_name, parent, data=None):
    validate_subject_exists(parent)
    validate_class_exists_in_graphdb(prop_name)
    
    # Generate UUID for the new instance
    new_inst_name = instance_name(use_uuid=True)
    new_inst_iri = serialize_iri(new_inst_name)
    
    # Retrieve range class of the property
    class_iri = serialize_iri(prop_name)
    
    parent_iri = serialize_subject(parent)
    pred_iri = get_property_iri(prop_name)
    
    triples = [
        f"{new_inst_iri} <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> {class_iri} .",
        f"{parent_iri} {pred_iri} {new_inst_iri} ."
    ]
    
    if data:
        # Preprocess / resolve labels to object references
        resolved_data = {}
        for prop, val in data.items():
            if isinstance(val, list):
                resolved_data[prop] = [resolve_val_sparql(prop, v) for v in val]
            else:
                resolved_data[prop] = resolve_val_sparql(prop, val)
                
        # Upfront validation for data properties
        for prop, val in resolved_data.items():
            values = val if isinstance(val, list) else [val]
            for v in values:
                if v is None or (isinstance(v, str) and not v.startswith("instance") and prop != "label"):
                    if is_object_property_in_graphdb(prop):
                        raise ValueError("Creation of nested individuals via direct SPARQL mutations is not supported in Milestone 2/3 except through explicit creation APIs.")
                if isinstance(v, str) and v.startswith("instance") and not instance_exists(v):
                    raise ValueError(f"Referenced instance {v} does not exist in GraphDB.")
                    
        for prop, val in resolved_data.items():
            p_iri = get_property_iri(prop)
            values = val if isinstance(val, list) else [val]
            for v in values:
                if v is not None:
                    obj_val = serialize_object(v)
                    triples.append(f"{new_inst_iri} {p_iri} {obj_val} .")
                    
    query = f"""
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    INSERT DATA {{
        GRAPH <http://coupled_modelling.owl> {{
            {" ".join(triples)}
        }}
    }}
    """
    sparql_update(query)
    return new_inst_name


def get_instance_properties_recursively(inst_name, depth=1, recursive=False):
    """
    Get instance properties and its subproperties recursively.

    Args:
        inst_name (str): Instance name.
        depth (int, optional): Depth of the recursion.
        recursive (bool, optional): If True, the depth of recursion is unlimited.

    Returns:
        Dictionary of nested properties.
    """
    props = get_instance_properties(inst_name)

    if recursive == True:
        depth = None

    if depth:
        depth -= 1
    
    if depth == None or depth > 0:                    
        for key, items in props.items():
            if type(items) == list:
                temp_list = []
                for item in items:
                    if onto[item]:
                        temp_list.append({item: get_instance_properties_recursively(item, depth, recursive)})
                    else:
                        temp_list.append(item)
                props[key] = temp_list
            else:
                if onto[items]:
                    props[key] = {items: get_instance_properties_recursively(items, depth, recursive)}
                else:
                    props[key] = items
    return props


def create_instance(prop, parent, data=None):
    inst = add_value(parent, prop)
    if data:
        for prop, value in data.items():
            add_value(inst, prop, value)
    return inst


def copy_instance(inst, parent=None, data=None):
    """
    Creates a structural copy of a given instance with all its properties.

    Args:
        inst_name (str): Instance name.
        parent_name (str, optional): Name of the parent instance.

    Returns:
        Created instance.
    """
    with onto:
        inst = onto[inst]
        cl = type(inst)
        new_inst = cl(instance_name(use_uuid=False))

        if parent:
            parent = onto[parent]
            prop = None
            for subj, p in inst.get_inverse_properties():
                prop = p
                if isinstance(subj, type(parent)):
                    break
            if prop is not None:
                prop[parent].append(new_inst)
            else:
                raise ValueError(f"Could not find any inverse property on {inst.name} to connect to parent {parent.name}")
        
        if data:
            new_props = data.keys()
        
        for prop in inst.get_properties():
            
            if data:
                if prop.name.replace('has_', '') in new_props:
                    continue

            objects = prop[inst]
            for obj in objects:
                if hasattr(obj, 'name'):
                    if not has_only_label(obj):
                        continue
                prop[new_inst].append(obj)
        
        if data:
            for prop, value in data.items():
                add_value(new_inst.name, prop, value)
        
        return new_inst.name


def copy_instance_recursively(inst, parent=None, data=None, depth=1, recursive=False, is_top=True):
    """
    Creates a structural copy of a given instance with all it properties revursively.

    Args:
        inst_name (str): Instance name.

    Returns:
        Created instance.
    """
    with onto:
        new_inst = copy_instance(inst, parent, data)
        new_inst = onto[new_inst]
        inst = onto[inst]
        
        if recursive == True:
            depth = None

        if depth:
            depth -= 1

        if depth == None or depth > 0:
            for prop in inst.get_properties():
                objects = prop[inst]
                for obj in objects:
                    if hasattr(obj, 'name'):
                        if not has_only_label(obj):
                            obj = copy_instance_recursively(obj.name, depth=depth, recursive=recursive, is_top=False)
                            obj = onto[obj]
                            prop[new_inst].append(obj)
        return new_inst.name


def export_coupled_kratos(coupled_system):
    """
    Returns a coupled system in Kratos format.

    Args:
        coupled_system_name (str): Name of the coupled system.

    Returns:
        Dictionary of nested properties.
    """
    props = get_instance_properties(coupled_system)
    label = None
    for key in list(props.keys()):
        if key == 'label':
            #label = props['label'][0]
            label = props['label']
    if label:
        props.pop('label', None)
    if 'coupled_system' in str(type(onto[coupled_system]).name):
        label = None
    result = props.pop('result', None)
    for key, items in props.items():
        if type(items) == list and len(items) > 1 and key in force_dict():
            temp_dict = {}
            for item in items:
                obj_props = export_coupled_kratos(item)
                temp_dict[list(obj_props.keys())[0]] = list(obj_props.values())[0]
            props[key] = temp_dict
        elif (type(items) == list and len(items) > 1) or key in force_list():
            temp_list = []
            for item in items:
                if onto[item]:
                    if has_only_label(onto[item]):
                        temp_list.append(onto[item].label[0])
                    else:
                        temp_list.append(export_coupled_kratos(item))
                else:
                    temp_list.append(item)
            props[key] = temp_list
        else:
            #item = items[0]
            inst = onto[items]
            if inst:
                if has_only_label(inst):
                    props[key] = inst.label[0]
                else:
                    props[key] = export_coupled_kratos(items)
            else:
                props[key] = items
    if label:
        props = {label: props}
    label = None
    return props


def force_dict():
    return ['solvers', 'data']


def force_list():
    return [
        'convergence_accelerators',
        'convergence_criteria',
        'input_data_list',
        'output_data_list',
        'export_data',
        'import_data',
        'import_meshes',
        'data_transfer_operator_options'
    ]


def get_connected_instances_recursively(inst_name, insts, depth):
    """
    For a given instance, returns its connected instances.

    Args:
        inst_name (str): Instance name.
        insts (list): List of instances.
        depth (int): Depth of the instance tree.

    Returns:
        A list of connected instance names.
    """
    inst = onto[inst_name]
    #if insts.get(inst):
    #    if insts[inst] > depth:
    #        pass
    #    else:
    #        insts[inst] = depth
    #else:
    insts[inst] = depth
    depth += 1
    for prop in inst.get_properties():
        for value in prop[inst]:
            if hasattr(value, 'name'):
                get_connected_instances_recursively(value.name, insts, depth)


def infer_class_properties(inst):
    """
    Infers new classes and axioms from a given instance.

    Args:
        inst (OWL instance): OWL-instance to infer from.
    """
    new_props = []
    for rel in inst.get_properties():
        if str(rel) == 'rdf-schema.label':
            continue
        for obj in rel[inst]:
            if hasattr(obj, 'is_a'):
                new_props.append((rel, And(obj.is_a)))
            else:
                new_props.append((rel, type(obj)))
    new_props = Counter(new_props)
    if not(len(new_props)):
        return
    new_classes = []
    for cl in inst.is_a:
        match = False
        subclasses = list(cl.subclasses())
        subclasses.append(cl)
        for sub_cl in subclasses:
            old_props = {}
            for x in sub_cl.is_a:
                if hasattr(x, 'property') and hasattr(x, 'value'):
                    old_props[(x.property, x.value)] = x.cardinality
            #old_props.pop('rdf-schema.label', None)
            if old_props == new_props:
                match = True
                #if sub_cl not in inst.is_a:
                new_classes.append(sub_cl)
                break
        if not match:
            n = len(list(cl.subclasses())) + 1
            new_cl = types.new_class(f'{cl.name}_{n}', (cl,))
            for (rel, obj_cl), card in new_props.items():
                new_cl.is_a.append(rel.exactly(card, obj_cl))
            #inst.is_a.remove(cl)
            new_classes.append(new_cl)
    inst.is_a = new_classes


def infer_class_properties_recursively(insts):
    max_depth = max([x for x in insts.values()])
    for inst, depth in list(insts.items()):
        if depth == max_depth:
            infer_class_properties(inst)
            del insts[inst]
    if len(insts):
        infer_class_properties_recursively(insts)


def infer_coupled_system_structure(coupled_system):
    insts = {}
    get_connected_instances_recursively(coupled_system, insts, 0)
    infer_class_properties_recursively(insts)


def import_coupled_kratos(data, label):
    """
    Recursively creates an OWL-instance of the coupled system class with given data and label.

    Args:
        data: Dictionary with the coupled system data.
        label: Label of the coupled system.

    Returns:
        The OWL-instance of the coupled system.
    """
    inst_name = create_coupled(label)
    inst = onto[inst_name]
    for pred_name, obj_data in data.items():
        inst = add_coupled_system(inst, pred_name, obj_data)
    infer_coupled_system_structure(inst_name)
    return inst_name


def get_class_hierarchy():
    """
    Returns a dictionary mapping root classes to their subclasses.
    """
    try:
        query = f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?class ?subClass WHERE {{
            GRAPH <{onto_uri}> {{
                ?class rdf:type owl:Class .
                FILTER (STRSTARTS(STR(?class), "http://coupled_modelling.owl#"))
                FILTER NOT EXISTS {{
                    ?class rdfs:subClassOf ?parent .
                    FILTER (?parent != owl:Thing && ?parent != ?class && STRSTARTS(STR(?parent), "http://coupled_modelling.owl#"))
                }}
                OPTIONAL {{
                    ?subClass rdfs:subClassOf ?class .
                    FILTER (?subClass != ?class)
                }}
            }}
        }}
        """
        res = query_graphdb(query)
        hierarchy = {}
        for binding in res.get("results", {}).get("bindings", []):
            class_name = get_local_name(binding["class"]["value"])
            if class_name not in hierarchy:
                hierarchy[class_name] = []
            if "subClass" in binding:
                subclass_name = get_local_name(binding["subClass"]["value"])
                if subclass_name not in hierarchy[class_name]:
                    hierarchy[class_name].append(subclass_name)
        return hierarchy
    except Exception as e:
        print(f"GraphDB query failed in get_class_hierarchy: {e}. Falling back to Owlready2.")
        res = {}
        for cl in onto.classes():
            if cl.is_a == [Thing]:
                res[cl.name] = [x.name for x in cl.subclasses()]
        return res

def get_graphdb_health():
    """
    Checks the health of the GraphDB connection and repository.
    Returns:
        dict: A dictionary containing health details.
    Raises:
        GraphDBError: If the repository or GraphDB is offline.
    """
    query = "ASK { ?s ?p ?o }"
    try:
        query_graphdb(query)
        return {
            "status": "ok",
            "graphdb": "connected",
            "repository": REPOSITORY
        }
    except Exception as e:
        if isinstance(e, GraphDBError):
            raise
        raise GraphDBError(f"Health check failed: {e}") from e


def select_preferred_label(labels, fallback):
    """
    Sorts labels prioritizing English, then untagged, then other languages,
    followed by case-insensitive lexical sorting.
    """
    if not labels:
        return fallback
    ordered = sorted(
        labels,
        key=lambda item: (
            0 if item[0].lower() == "en" else
            1 if item[0] == "" else
            2,
            item[0].lower(),
            item[1].casefold()
        )
    )
    return ordered[0][1]


def get_class_hierarchy_metadata():
    """
    Returns the complete class list with parent arrays, filtered for project local classes.
    """
    query = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    SELECT DISTINCT ?class ?parent WHERE {{
        GRAPH <{onto_uri}> {{
            ?class rdf:type owl:Class .
            FILTER (STRSTARTS(STR(?class), "http://coupled_modelling.owl#"))
            OPTIONAL {{
                ?class rdfs:subClassOf ?parent .
                FILTER (?parent != owl:Thing && ?parent != ?class && STRSTARTS(STR(?parent), "http://coupled_modelling.owl#"))
            }}
        }}
    }}
    """
    res = query_graphdb(query)
    class_parents = {}
    for binding in res.get("results", {}).get("bindings", []):
        class_name = get_local_name(binding["class"]["value"])
        if class_name not in class_parents:
            class_parents[class_name] = set()
        if "parent" in binding:
            parent_name = get_local_name(binding["parent"]["value"])
            class_parents[class_name].add(parent_name)
            
    result = []
    for cl_name, parents in class_parents.items():
        result.append({
            "class": cl_name,
            "parents": sorted(list(parents))
        })
    result.sort(key=lambda x: x["class"])
    return result


def get_class_instance_summaries(class_name):
    """
    Returns instance summaries containing unique ID, label, and direct types list.
    """
    validate_class_exists_in_graphdb(class_name)
    class_iri = get_uri(class_name)
    query = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?inst ?label (LANG(?label) AS ?lang) ?type WHERE {{
        GRAPH <{onto_uri}> {{
            ?inst rdf:type/rdfs:subClassOf* <{class_iri}> .
            ?inst rdf:type ?type .
            FILTER (STRSTARTS(STR(?type), "http://coupled_modelling.owl#"))
            OPTIONAL {{
                ?inst rdfs:label ?label .
            }}
        }}
    }}
    """
    res = query_graphdb(query)
    inst_data = {}
    for binding in res.get("results", {}).get("bindings", []):
        inst_uri = binding["inst"]["value"]
        inst_id = get_local_name(inst_uri)
        type_uri = binding["type"]["value"]
        type_name = get_local_name(type_uri)
        
        if inst_id not in inst_data:
            inst_data[inst_id] = {
                "labels": [],
                "types": set()
            }
        
        inst_data[inst_id]["types"].add(type_name)
        if "label" in binding:
            lang = binding.get("lang", {}).get("value", "")
            val = binding["label"]["value"]
            inst_data[inst_id]["labels"].append((lang, val))
            
    summaries = []
    for inst_id, data in inst_data.items():
        selected_label = select_preferred_label(data["labels"], inst_id)
        summaries.append({
            "id": inst_id,
            "label": selected_label,
            "types": sorted(list(data["types"]))
        })
    summaries.sort(key=lambda x: x["label"])
    return summaries


def get_instance_property_metadata(inst_name):
    """
    Retrieves direct outgoing statements for a selected instance with type metadata.
    """
    validate_subject_exists(inst_name)
    inst_uri = get_uri(inst_name)
    
    q1 = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?label (LANG(?label) AS ?lang) ?type WHERE {{
        GRAPH <{onto_uri}> {{
            <{inst_uri}> rdf:type ?type .
            OPTIONAL {{
                <{inst_uri}> rdfs:label ?label .
            }}
        }}
    }}
    """
    
    q2 = f"""
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?prop ?obj ?obj_label (LANG(?obj_label) AS ?obj_lang) WHERE {{
        GRAPH <{onto_uri}> {{
            <{inst_uri}> ?prop ?obj .
            FILTER (?prop != rdf:type)
            OPTIONAL {{
                FILTER(isIRI(?obj))
                ?obj rdfs:label ?obj_label .
            }}
        }}
    }}
    """
    
    r1 = query_graphdb(q1)
    r2 = query_graphdb(q2)
    
    labels = []
    types = set()
    for binding in r1.get("results", {}).get("bindings", []):
        if "label" in binding:
            lang = binding.get("lang", {}).get("value", "")
            val = binding["label"]["value"]
            labels.append((lang, val))
        if "type" in binding:
            type_uri = binding["type"]["value"]
            if type_uri.startswith("http://coupled_modelling.owl#"):
                types.add(get_local_name(type_uri))
                
    resolved_label = select_preferred_label(labels, inst_name)
    
    prop_objects = {}
    prop_literals = {}
    
    for binding in r2.get("results", {}).get("bindings", []):
        prop_uri = binding["prop"]["value"]
        prop_name = get_local_name(prop_uri).replace('has_', '')
        
        obj_binding = binding["obj"]
        obj_type = obj_binding.get("type")
        obj_val = obj_binding["value"]
        
        if obj_type == "uri" and obj_val.startswith("http://coupled_modelling.owl#"):
            obj_id = get_local_name(obj_val)
            if prop_name not in prop_objects:
                prop_objects[prop_name] = {}
            if obj_id not in prop_objects[prop_name]:
                prop_objects[prop_name][obj_id] = []
            if "obj_label" in binding:
                obj_lang = binding.get("obj_lang", {}).get("value", "")
                obj_lbl = binding["obj_label"]["value"]
                prop_objects[prop_name][obj_id].append((obj_lang, obj_lbl))
        else:
            datatype = "http://www.w3.org/2001/XMLSchema#anyURI" if obj_type == "uri" else obj_binding.get("datatype", "http://www.w3.org/2001/XMLSchema#string")
            val = obj_val
            if datatype == "http://www.w3.org/2001/XMLSchema#integer":
                try:
                    val = int(obj_val)
                except ValueError:
                    pass
            elif datatype in ("http://www.w3.org/2001/XMLSchema#double", "http://www.w3.org/2001/XMLSchema#float"):
                try:
                    val = float(obj_val)
                except ValueError:
                    pass
            elif datatype == "http://www.w3.org/2001/XMLSchema#boolean":
                val = (obj_val.lower() == "true")
            
            literal_dict = {
                "kind": "literal",
                "value": val,
                "datatype": datatype
            }
            if "xml:lang" in obj_binding:
                literal_dict["language"] = obj_binding["xml:lang"]
            if prop_name not in prop_literals:
                prop_literals[prop_name] = []
            prop_literals[prop_name].append(literal_dict)
            
    properties_map = {}
    for prop_name, obj_dict in prop_objects.items():
        if prop_name not in properties_map:
            properties_map[prop_name] = []
        for obj_id, labels_list in obj_dict.items():
            selected_obj_lbl = select_preferred_label(labels_list, obj_id)
            properties_map[prop_name].append({
                "kind": "object",
                "id": obj_id,
                "label": selected_obj_lbl
            })
            
    for prop_name, literal_list in prop_literals.items():
        if prop_name not in properties_map:
            properties_map[prop_name] = []
        properties_map[prop_name].extend(literal_list)
        
    properties_list = []
    for prop_name, values in properties_map.items():
        values.sort(key=lambda x: str(x.get("label", x.get("value", ""))))
        properties_list.append({
            "property": prop_name,
            "values": values
        })
    properties_list.sort(key=lambda x: x["property"])
    
    return {
        "id": inst_name,
        "label": resolved_label,
        "types": sorted(list(types)),
        "properties": properties_list
    }


onto_uri = 'http://coupled_modelling.owl'
# default_world.set_backend(filename = get_db_path())

try:
    onto = load_onto()
except Exception as e:
    print(f"Failed to load onto: {e}")
    onto = new_onto()