import os

from flask import *
from main import *


app = Flask(__name__)

# Cross-origin access for the separate Next.js frontend (coupled-modelling-frontend).
# Comma-separated list of allowed origins; defaults to the local frontend dev server.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
    if origin.strip()
]


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin and (origin in CORS_ALLOWED_ORIGINS or '*' in CORS_ALLOWED_ORIGINS):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Max-Age'] = '86400'
    return response


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/v1.0/openapi.yaml', methods=['GET'])
def api_openapi_spec():
    spec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'openapi.yaml')
    return send_file(spec_path, mimetype='application/yaml')


@app.route('/api/v1.0/health/', methods=['GET'])
def api_health():
    try:
        health_data = get_graphdb_health()
        return jsonify(health_data), 200
    except GraphDBError as e:
        return jsonify(status="error", graphdb="unavailable", repository=REPOSITORY, error=str(e)), 503
    except Exception as e:
        return jsonify(status="error", graphdb="unavailable", repository=REPOSITORY, error=str(e)), 500


@app.route('/api/v1.0/get_class_hierarchy_metadata/', methods=['GET'])
def api_get_class_hierarchy_metadata():
    try:
        hierarchy = get_class_hierarchy_metadata()
        return jsonify(hierarchy), 200
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/api/v1.0/get_class_instance_summaries/', methods=['GET'])
def api_get_class_instance_summaries():
    class_name = request.args.get('class')
    try:
        summaries = get_class_instance_summaries(class_name)
        return jsonify(summaries), 200
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/v1.0/get_class_metadata/', methods=['GET'])
def api_get_class_metadata():
    class_name = request.args.get('class')
    if not class_name:
        return jsonify(error="Missing required query parameter: class"), 400
    try:
        metadata = get_class_metadata(class_name)
        return jsonify(metadata), 200
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/api/v1.0/get_instance_property_metadata/', methods=['GET'])
def api_get_instance_property_metadata():
    inst_name = request.args.get('instance')
    if not inst_name:
        return jsonify(error="Missing required query parameter: instance"), 400
    try:
        metadata = get_instance_property_metadata(inst_name)
        return jsonify(metadata), 200
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route('/api/v1.0/import_coupled_kratos/', methods=['POST'])
def api_import_coupled_kratos():
    args = request.get_json()
    data = args.get('data')
    label = args.get('label')
    try:
        reload_ontology_from_graphdb()
        inst = import_coupled_kratos(data, label)
        save_onto()
        return jsonify(inst), 201
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/create_coupled/', methods=['POST'])
def api_create_coupled():
    args = request.get_json()
    label = args.get('label')
    try:
        reload_ontology_from_graphdb()
        inst = create_coupled(label)
        save_onto()
        return jsonify(inst), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/copy_instance_recursively/', methods=['POST'])
def api_copy_instance_recursively():
    args = request.get_json()
    inst = args.get('instance')
    parent = args.get('parent')
    data = args.get('data')
    depth = args.get('depth')
    recursive = args.get('recursive')
    if depth:
        depth = int(depth)
    if recursive == 'True':
        recursive = True
    else:
        recursive = False
        
    try:
        reload_ontology_from_graphdb()
        inst = copy_instance_recursively(inst, parent, data, depth, recursive)
        save_onto()
        return jsonify(inst), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/copy_instance/', methods=['POST'])
def api_copy_instance():
    args = request.get_json()
    inst = args.get('instance')
    parent = args.get('parent')
    data = args.get('data')
    try:
        reload_ontology_from_graphdb()
        new_inst = copy_instance(inst, parent, data)
        save_onto()
        return jsonify(new_inst), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/create_instance/', methods=['POST'])
def api_create_instance():
    args = request.get_json()
    prop = args.get('property')
    parent = args.get('parent')
    data = args.get('data')
    try:
        inst = create_instance_sparql(prop, parent, data)
        return jsonify(inst), 201
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/api/v1.0/get_instance_properties_recursively/', methods=['GET'])
def api_get_instance_properties_recursively():
    args = request.args
    inst = args.get('instance')
    depth = args.get('depth')
    recursive = args.get('recursive')
    if depth:
        depth = int(depth)
    if recursive == 'True':
        recursive = True
    else:
        recursive = False
        
    try:
        reload_ontology_from_graphdb()
        props = get_instance_properties_recursively(inst, depth, recursive)
        return jsonify(props), 200
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/replace_values/', methods=['POST'])
def api_replace_values():
    args = request.get_json()
    inst = args.get('instance')
    data = args.get('data')
    try:
        replace_values_sparql(inst, data)
        return jsonify(''), 201
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/api/v1.0/delete_values/', methods=['POST'])
def api_delete_values():
    args = request.get_json()
    inst = args.get('instance')
    props = args.get('properties')
    try:
        delete_values_sparql(inst, props)
        return jsonify(''), 201
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/api/v1.0/add_values/', methods=['POST'])
def api_add_values():
    args = request.get_json()
    inst = args.get('instance')
    data = args.get('data')
    try:
        add_values_sparql(inst, data)
        return jsonify(''), 201
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/api/v1.0/replace_properties/', methods=['POST'])
def api_replace_properties():
    args = request.get_json()
    inst = args.get('instance')
    data = args.get('data')
    try:
        replace_properties_sparql(inst, data)
        return jsonify(''), 201
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/api/v1.0/infer_coupled_structure/', methods=['POST'])
def api_infer_coupled_structure():
    args = request.get_json()
    inst = args.get('coupled_system')
    try:
        reload_ontology_from_graphdb()
        infer_coupled_system_structure(inst)
        save_onto()
        return jsonify(''), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/export_coupled_kratos/', methods=['POST'])
def api_export_coupled_kratos():
    args = request.get_json()
    inst = args.get('coupled_system')
    try:
        reload_ontology_from_graphdb()
        export = export_coupled_kratos(inst)
        return jsonify(export), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/save_onto/', methods=['POST'])
def api_save_onto():
    try:
        save_onto()
        return jsonify(''), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/save_locally/', methods=['GET'])
def api_save_locally():
    try:
        reload_ontology_from_graphdb()
        save_locally()
        return send_file(get_onto_path()), 200
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/get_class_hierarchy/', methods=['GET'])
def api_get_class_hierarchy():
    try:
        classes = get_class_hierarchy()
        return jsonify(classes), 200
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/get_class_properties_recursively/', methods=['GET'])
def api_get_class_properties_recursively():
    args = request.args
    cl = args.get('class')
    depth = args.get('depth')
    recursive = args.get('recursive')
    if depth:
        depth = int(depth)
    if recursive == 'True':
        recursive = True
    else:
        recursive = False
    try:
        reload_ontology_from_graphdb()
        props = get_class_properties_recursively(cl, depth, recursive)
        return jsonify(props), 200
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/get_class_instances/', methods=['GET'])
def api_get_class_instances():
    try:
        cl = request.args.get('class')
        insts = get_class_instances(cl)
        return jsonify(insts), 200
    except Exception as e:
        return jsonify(error=str(e)), 400
    

@app.route('/api/v1.0/delete_value/', methods=['POST'])
def api_delete_value():
    args = request.get_json()
    inst = args.get('instance')
    prop = args.get('property')
    value_obj = args.get('value')
    
    if not inst or not prop or value_obj is None:
        return jsonify(error="instance, property, and value parameters are required"), 400
        
    try:
        delete_value_sparql(inst, prop, value_obj)
        return jsonify(''), 201
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/api/v1.0/create_class_instance/', methods=['POST'])
def api_create_class_instance():
    args = request.get_json()
    class_name = args.get('class')
    label = args.get('label')
    
    if not class_name or not label:
        return jsonify(error="class and label parameters are required"), 400
        
    try:
        new_name = create_class_instance_sparql(class_name, label)
        return jsonify(new_name), 201
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/api/v1.0/delete_instance/', methods=['POST'])
def api_delete_instance():
    args = request.get_json() or {}
    instance_name = args.get('instance')
    
    if not instance_name:
        return jsonify(error="instance parameter is required"), 400
        
    try:
        delete_instance_sparql(instance_name)
        return jsonify(status="success", instance=instance_name), 200
    except GraphDBError as e:
        return jsonify(error=str(e)), 503
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=str(e)), 500



@app.route('/api/v1.0/download_owl/', methods=['GET'])
def api_download_owl():
    try:
        reload_ontology_from_graphdb()
        save_locally()
        return send_file(get_onto_path(), as_attachment=True, mimetype="application/rdf+xml")
    except Exception as e:
        return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run()
