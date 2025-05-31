import os
import logging
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from pdf2image import convert_from_path
import pytesseract
from transaction_parser import TransactionParser

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure maximum file size (16MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename):
    """Check if the uploaded file is a PDF"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

@app.route('/ocr', methods=['POST'])
def extract_transactions():
    """
    Extract banking transactions from uploaded PDF statement
    
    Expects:
    - file: PDF bank statement (form-data)
    
    Returns:
    - JSON array of transactions with date, description, amounts, and balance
    """
    try:
        # Check if file is present in request
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided. Please upload a PDF file using the "file" field.'}), 400
        
        file = request.files['file']
        
        # Check if file was selected
        if file.filename == '':
            return jsonify({'error': 'No file selected. Please choose a PDF file to upload.'}), 400
        
        # Validate file type
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Please upload a PDF file.'}), 400
        
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save uploaded file
            filename = secure_filename(file.filename or 'uploaded.pdf')
            file_path = os.path.join(temp_dir, filename)
            file.save(file_path)
            
            logging.debug(f"Processing PDF file: {filename}")
            
            # Convert PDF to images with optimized settings
            try:
                images = convert_from_path(
                    file_path,
                    dpi=200,  # Reduced from 300 for faster processing
                    output_folder=temp_dir,
                    fmt='png',
                    first_page=1,
                    last_page=5  # Limit to first 5 pages for faster processing
                )
                logging.debug(f"Converted PDF to {len(images)} images")
            except Exception as e:
                logging.error(f"Error converting PDF to images: {str(e)}")
                return jsonify({'error': f'Failed to process PDF file. Please ensure it is a valid PDF: {str(e)}'}), 400
            
            # Extract text from each page using OCR
            all_text_lines = []
            for i, image in enumerate(images):
                try:
                    # Perform OCR with French language and optimized config
                    text = pytesseract.image_to_string(
                        image,
                        lang='fra',
                        config='--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZàâäéèêëïîôöùûüÿçÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÇ€.,-: '
                    )
                    
                    # Split into lines and filter empty ones
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    all_text_lines.extend(lines)
                    
                    logging.debug(f"Page {i+1}: Extracted {len(lines)} text lines")
                    
                except Exception as e:
                    logging.error(f"OCR error on page {i+1}: {str(e)}")
                    continue
            
            if not all_text_lines:
                return jsonify({'error': 'No text could be extracted from the PDF. Please ensure it contains readable text.'}), 400
            
            # Parse transactions from extracted text
            parser = TransactionParser()
            transactions = parser.parse_transactions(all_text_lines)
            
            logging.debug(f"Extracted {len(transactions)} transactions")
            
            return jsonify(transactions)
            
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': f'An unexpected error occurred while processing your request: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'OCR Bank Extractor'})

@app.route('/test-parser', methods=['GET'])
def test_parser():
    """Test the transaction parser with sample data from your PDF"""
    sample_lines = [
        "1 avr. 2025                                Cigusto Orleans                                                                                               €5.90                                                                                             €30.61",
        "1 avr. 2025                                Carrefour                                                                                                     €2.54                                                                                             €28.07", 
        "3 avr. 2025                                Payment from Adwork's                                                                                                                         €590.00                                 €593.94",
        "4 avr. 2025                                Tabac Presse Le Score                                                           €26.00                                                                €574.44"
    ]
    
    parser = TransactionParser()
    transactions = parser.parse_transactions(sample_lines)
    
    return jsonify({
        'message': 'Parser test with sample transactions from your PDF',
        'transactions_found': len(transactions),
        'transactions': transactions
    })

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large. Maximum file size is 16MB.'}), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found. Use POST /ocr to extract transactions from PDF.'}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({'error': 'Method not allowed. Use POST method for /ocr endpoint.'}), 405

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
