from flask import request, jsonify
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
        return f(*args, **kwargs)
    return wrapper