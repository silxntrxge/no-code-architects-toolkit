from flask import request, jsonify, current_app
from functools import wraps
import jsonschema

def validate_payload(schema):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.json:
                return jsonify({"message": "Missing JSON in request"}), 400
            try:
                jsonschema.validate(instance=request.json, schema=schema)
            except jsonschema.exceptions.ValidationError as validation_error:
                return jsonify({"message": f"Invalid payload: {validation_error.message}"}), 400
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def rate_limited(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Implement rate limiting logic here if needed
        return f(*args, **kwargs)
    return decorated_function

def bypass_queue(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if hasattr(current_app, 'queue_task'):
            return current_app.queue_task(bypass_queue=True)(f)(*args, **kwargs)
        # Extract job_id and data from the request and pass them to the function
        data = request.json
        job_id = data.get('id', 'default_job_id')
        return f(job_id, data)
    return wrapper

def queue_task_wrapper(bypass_queue=False):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if hasattr(current_app, 'queue_task'):
                return current_app.queue_task(bypass_queue=bypass_queue)(f)(*args, **kwargs)
            # Extract job_id and data from the request and pass them to the function
            data = request.json
            job_id = data.get('id', 'default_job_id')
            return f(job_id, data)
        return wrapper
    return decorator