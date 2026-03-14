from flask import Flask, request, send_file, jsonify
from rembg import remove
from PIL import Image, ImageFilter
import os
from io import BytesIO
import uuid
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv('API_KEY', '').strip()
ORIGINAL_DIR = 'original'
MASKED_DIR = 'masked'

# Set up directories
os.makedirs(ORIGINAL_DIR, exist_ok=True)
os.makedirs(MASKED_DIR, exist_ok=True)

def sanitize_filename(filename):
    sanitized_filename = secure_filename(filename or '')
    return sanitized_filename or 'upload_image'

def _parse_blur_radius(raw_value, default=10):
    try:
        blur_radius = float(raw_value)
    except (TypeError, ValueError):
        return default

    return max(0.0, min(100.0, blur_radius))

def _verify_api_key():
    if not API_KEY:
        return jsonify({'error': 'Server API key is not configured'}), 500

    provided_key = request.headers.get('x-api-key', '').strip()
    if provided_key != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401

    return None

def process_image(file, blur_radius=10):
    # Generate a unique sanitized filename to avoid collisions.
    sanitized_filename = sanitize_filename(file.filename)
    filename_root, extension = os.path.splitext(sanitized_filename)
    unique_suffix = uuid.uuid4().hex[:8]
    original_filename = f"{filename_root}_{unique_suffix}{extension or '.png'}"
    output_filename = f"{filename_root}_{unique_suffix}_blurred.jpg"

    # Save the uploaded image inside the "original" folder with the sanitized filename
    input_data = file.read()
    original_image_path = os.path.join(ORIGINAL_DIR, original_filename)
    with open(original_image_path, 'wb') as original_file:
        original_file.write(input_data)

    # Remove the background from the uploaded image
    foreground_img = Image.open(BytesIO(remove(input_data, alpha_matting=True))).convert('RGBA')

    # Save the foreground image in the "masked" folder with the sanitized filename
    foreground_path = os.path.join(MASKED_DIR, f"{filename_root}_{unique_suffix}_foreground.png")
    foreground_img.save(foreground_path, format='PNG')

    # Open original image from memory and apply blur only on background.
    original_img = Image.open(BytesIO(input_data)).convert('RGBA')

    # Apply lens blur to the entire original image
    blurred_original = original_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # Composite the foreground onto the blurred original image
    final_img = Image.alpha_composite(blurred_original.convert('RGBA'), foreground_img)

    # Save final image to disk and return it as memory buffer for API response.
    composite_image_path = os.path.join(MASKED_DIR, output_filename)
    final_img.convert('RGB').save(composite_image_path, format='JPEG', quality=95)

    image_buffer = BytesIO()
    final_img.convert('RGB').save(image_buffer, format='JPEG', quality=95)
    image_buffer.seek(0)

    return image_buffer, output_filename

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

@app.route('/api/blur-background', methods=['POST'])
def blur_background_api():
    auth_error = _verify_api_key()
    if auth_error:
        return auth_error

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in request'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    blur_radius = _parse_blur_radius(request.form.get('blur-radius', 10))

    try:
        image_buffer, output_filename = process_image(file, blur_radius)
    except Exception as exc:
        return jsonify({'error': f'Image processing failed: {str(exc)}'}), 500

    return send_file(
        image_buffer,
        mimetype='image/jpeg',
        as_attachment=False,
        download_name=output_filename,
    )

@app.route('/', methods=['GET'])
def root_route():
    return jsonify({
        'service': 'background-blur-api',
        'endpoint': '/api/blur-background',
        'method': 'POST',
        'auth_header': 'x-api-key',
        'form_fields': ['file', 'blur-radius (optional, 0-100)']
    })

if __name__ == '__main__':
    app.run(debug=True)