from flask import Flask, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
from api.routes import api_bp
from config import get_config

# Load environment variables
load_dotenv()

def create_app():
    # Initialize Flask app
    app = Flask(__name__)
    
    # Load configuration
    app_config = get_config()
    app.config.from_object(app_config)
    
    # Configure CORS
    CORS(app)
    
    # Register blueprints
    app.register_blueprint(api_bp)
    
    # Default route
    @app.route('/', methods=['GET'])
    def index():
        return jsonify({"message": "Welcome to Portagees API"}), 200
    
    return app

# Run the app
if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 