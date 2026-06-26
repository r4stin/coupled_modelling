from flask import *
from main import *


app = Flask(__name__)

@app.route('/api/v1.0/import_coupled_kratos/', methods=['POST'])
def api_import_coupled_kratos():
    args = request.get_json()
    data = args.get('data')
    label = args.get('label')
    try:
        load_before_mutate()
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
        load_before_mutate()
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
        load_before_mutate()
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
        load_before_mutate()
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
        load_before_mutate()
        inst = create_instance(prop, parent, data)
        save_onto()
        return jsonify(inst), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


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
        props = get_instance_properties_recursively(inst, depth, recursive)
        return jsonify(props), '200'
    except:
        return '400'


@app.route('/api/v1.0/replace_values/', methods=['POST'])
def api_replace_values():
    args = request.get_json()
    inst = args.get('instance')
    data = args.get('data')
    try:
        load_before_mutate()
        replace_values(inst, data)
        save_onto()
        return jsonify(''), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/delete_values/', methods=['POST'])
def api_delete_values():
    args = request.get_json()
    inst = args.get('instance')
    props = args.get('properties')
    try:
        load_before_mutate()
        delete_values(inst, props)
        save_onto()
        return jsonify(''), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/add_values/', methods=['POST'])
def api_add_values():
    args = request.get_json()
    inst = args.get('instance')
    data = args.get('data')
    try:
        load_before_mutate()
        add_values(inst, data)
        save_onto()
        return jsonify(''), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/replace_properties/', methods=['POST'])
def api_replace_properties():
    args = request.get_json()
    inst = args.get('instance')
    data = args.get('data')
    try:
        load_before_mutate()
        replace_properties(inst, data)
        save_onto()
        return jsonify(''), 201
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route('/api/v1.0/infer_coupled_structure/', methods=['POST'])
def api_infer_coupled_structure():
    args = request.get_json()
    inst = args.get('coupled_system')
    try:
        load_before_mutate()
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
    

if __name__ == "__main__":
    app.run()
