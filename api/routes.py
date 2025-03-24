from flask import Blueprint, jsonify, request

# Create a Blueprint for our API routes
api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint to verify API status"""
    return jsonify({"status": "ok", "message": "API is running"}), 200

@api_bp.route('/hello', methods=['GET'])
def hello():
    """Simple hello endpoint"""
    return jsonify({"message": "Hello from Portagees API!"}), 200

# Example route with path parameter
@api_bp.route('/user/<user_id>', methods=['GET'])
def get_user(user_id):
    """Example endpoint with path parameter"""
    # This is just a placeholder - in a real app, you would fetch from a database
    return jsonify({"user_id": user_id, "name": "Sample User"}), 200

# Example route with query parameters and POST method
@api_bp.route('/data', methods=['POST'])
def create_data():
    """Example endpoint for POST requests with JSON data"""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
        
    # Process the data (this is just an example)
    return jsonify({"message": "Data received", "data": data}), 201 