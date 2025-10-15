#!/usr/bin/env python3
"""
POLARIS MVP - AI-Powered Wealth Planning Platform
Entry point for production deployment
"""

import os
import sys
from datetime import datetime, UTC

from flask import jsonify

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import the Flask app from main.py
from src.main import create_app

app = create_app()


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(UTC).isoformat(),
    })


if __name__ == '__main__':
    # Get port from environment variable or default to 5000
    port = int(os.environ.get('PORT', 5000))

    # Run the app
    app.run(host='0.0.0.0', port=port, debug=False)
