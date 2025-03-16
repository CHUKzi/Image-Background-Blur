from flask import Flask, request, render_template, send_file
from rembg import remove
from PIL import Image, ImageFilter
import os
from io import BytesIO
import re

app = Flask(__name__)

# Set up directories
os.makedirs('original', exist_ok=True)
os.makedirs('masked', exist_ok=True)

def sanitize_filename(filename):
    # Generate a sanitized filename without special characters and spaces
    sanitized_filename = re.sub(r'[^\w\s.-]', '', filename)
    sanitized_filename = sanitized_filename.replace(' ', '_')  # Replace spaces with underscores
    return sanitized_filename

def process_image(file, blur_radius=10):
    # Generate a sanitized filename
    sanitized_filename = sanitize_filename(file.filename)

    # Save the uploaded image inside the "original" folder with the sanitized filename
    original_image_path = os.path.join('original', sanitized_filename)
    file.save(original_image_path)

    # Remove the background from the uploaded image
    with open(original_image_path, 'rb') as f:
        input_data = f.read()
        foreground_img = Image.open(BytesIO(remove(input_data, alpha_matting=True)))

    # Save the foreground image in the "masked" folder with the sanitized filename
    foreground_path = os.path.join('masked', sanitized_filename)
    foreground_img.convert('RGBA').save(foreground_path, format='png')

    # Open the original image again
    with open(original_image_path, 'rb') as f:
        input_data = f.read()
        original_img = Image.open(BytesIO(input_data))

    # Apply lens blur to the entire original image
    blurred_original = original_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # Composite the foreground onto the blurred original image
    final_img = Image.alpha_composite(blurred_original.convert('RGBA'), foreground_img)

    # Save the final composite image in the "masked" folder with the sanitized filename
    composite_image_path = os.path.join('masked', sanitized_filename)
    final_img.convert('RGB').save(composite_image_path, format='jpeg')

    return composite_image_path

@app.route('/', methods=['GET', 'POST'])
def upload_and_process():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('index.html', error="No file part")

        file = request.files['file']
        
        if file.filename == '':
            return render_template('index.html', error="No selected file")

        if file:
            blur_radius = int(request.form.get('blur-radius', 10))  # Get blur radius from form, default to 10
            result_image_path = process_image(file, blur_radius)
            return render_template('result.html', result_image_path=result_image_path, basename=os.path.basename)

    return render_template('index.html')

@app.route('/masked/<filename>')
def serve_processed_image(filename):
    folder = 'masked'
    return send_file(os.path.join(folder, filename), mimetype='image/jpeg')

@app.route('/download/<filename>')
def download_processed_image(filename):
    folder = 'masked'
    return send_file(os.path.join(folder, filename), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)