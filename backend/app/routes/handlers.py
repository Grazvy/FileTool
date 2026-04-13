from flask import Blueprint, jsonify

api_bp = Blueprint('api', __name__)

@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'File Tool backend is running'})

@api_bp.route('/process', methods=['POST'])
def process_files():
    """Placeholder for file processing endpoint"""
    return jsonify({'status': 'not_implemented', 'message': 'File processing not yet implemented'})