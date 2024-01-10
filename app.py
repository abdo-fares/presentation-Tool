from flask import Flask, render_template, request, redirect, url_for, Response
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import yaml
import openai
import fitz
from io import BytesIO
import traceback
import requests
from reportlab.platypus import Image
import openai

from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image as PILImage
from io import BytesIO
import os

app = Flask(__name__)

# Load API key from config.yaml
with open("config.yaml") as f:
    config_yaml = yaml.load(f, Loader=yaml.FullLoader)
openai.api_key = config_yaml['token']


# Define a global variable to store the DALL·E generated image URL
dalle_generated_image_url = None


global x
x = None
# Helper function to save the uploaded PDF file
def save_pdf_file(pdf_file):
    if pdf_file:
        pdf_file_path = f"uploads/{pdf_file.filename}"
        pdf_file.save(pdf_file_path)
        return pdf_file_path
    return None

# Helper function to extract text from the PDF
def extract_text_from_pdf(pdf_file_path, page_selection):
    extracted_text = ''
    try:
        pdf_document = fitz.open(pdf_file_path)
        page_nums = []

        if page_selection:
            # Split the page_selection string into individual parts (pages and ranges)
            selections = page_selection.split(',')
            for part in selections:
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    page_nums.extend(range(start, end + 1))  # +1 to include the end page
                else:
                    page_nums.append(int(part))

            # Remove duplicates and sort the pages
            page_nums = sorted(set(page_nums))
        else:
            # If no page selection is provided, select all pages
            page_nums = range(1, len(pdf_document) + 1)

        for page_num in page_nums:
            page = pdf_document[page_num - 1]  # Adjust to 0-based indexing
            page_text = page.get_text()
            extracted_text += page_text
            print(f"Extracted text from page {page_num}:\n{page_text}\n{'=' * 50}\n")

    except ValueError as ve:
        print(f"Error: {str(ve)}")
    except Exception as e:
        print(f"Error extracting text from PDF: {str(e)}")

    return extracted_text




# Helper function to interact with ChatGPT and generate presentation content
def generate_presentation_content(extracted_text, keywords, question):
    global x
    additional_instructions = request.form.get('additional_instructions', '')
    try:
        # Formulate the prompt for GPT
        prompt = (
            f"Ich benötige einen nicht mehr als 350 worter Fließtext, der die wesentlichen Inhalte einer detaillierten und gründlichen Präsentation zusammenfasst. "
            f"Der Fließtext soll die Hauptpunkte der Präsentation mit klaren Formulierungen zusammenfassen und einen Schwerpunkt auf die folgenden Schlüsselwörter legen: {keywords}. "
            f"Zusätzliche Anweisungen: {additional_instructions} "
            f"Der Text der Präsentation lautet: {extracted_text}\n\n"
            "Bitte beginnen Sie mit einer kurzen Einführung, die einen Überblick über die Hauptthemen der Präsentation bietet, gefolgt von einer kompakten Zusammenfassung der einzelnen Abschnitte. "
            "Schließen Sie den Fließtext mit den wichtigsten Erkenntnissen und Schlussfolgerungen ab."
        )

        if question:
            prompt += f" {question}"

        # Log the inputs
        #print(f"Prompt: {prompt}")

        # Send API requests to GPT-4 using the chat completions endpoint
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        # Log the response
        if 'choices' not in completion or not completion['choices']:
            print("No choices in the completion response.")
            return None

        presentation_content = completion['choices'][0]['message'

        ]['content'].strip()

        if not presentation_content:
            print("Received empty content from GPT.")
            return None
        x = presentation_content
       # print(f"Generated Content: {presentation_content[:500]}...")  # Log the first 500 characters of the content
        return presentation_content

    except Exception as e:
        print(f"Error generating presentation content: {str(e)}")
        traceback.print_exc()
        return None


def split_text_into_parts(text, num_parts=3, max_length=800):
    # Split the text into words
    words = text.split()
    parts = [''] * num_parts
    current_part = 0

    for word in words:
        if current_part >= num_parts:
            break

        # Check if adding the next word would exceed the max_length
        if len(parts[current_part] + word) >= max_length:
            # Trim the text to max_length
            parts[current_part] = parts[current_part][:max_length]
            current_part += 1

        if current_part < num_parts:
            # Add the word to the current part
            if parts[current_part]:
                parts[current_part] += ' '
            parts[current_part] += word

    # Ensure all parts are trimmed to max_length
    for i in range(num_parts):
        parts[i] = parts[i][:max_length]

    return parts



# Helper function to generate a PDF document



def generate_pdf_with_image(presentation_content, image_urls):
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
        styles = getSampleStyleSheet()

        Story = []
        style = styles["Normal"]

        # Add the main presentation content
        p = Paragraph(presentation_content, style)
        Story.append(p)
        Story.append(Spacer(1, 12))

        # Add images
        for image_url in image_urls:
            if image_url:
                image_response = requests.get(image_url)
                if image_response.status_code == 200:
                    image_data = BytesIO(image_response.content)
                    image = Image(image_data, width=5.5 * inch, height=4 * inch)
                    Story.append(image)
                else:
                    print(f"Failed to download image from {image_url}")
            Story.append(Spacer(1, 12))

        doc.build(Story)
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Error generating PDF with image: {str(e)}")
        return None

def generate_dalle_images_urls(texts, photo_description, max_length=750):
    image_urls = []
    for i, text in enumerate(texts):
        try:
            # Truncate text to ensure it's within the character limit
            truncated_text = text[:max_length].strip()

            prompt = f"Read this following text understand what its main topic is and generate a creative image based on the main theme of it ,dont generate any images that include text !: {truncated_text}"
            if photo_description:
                additional_length = len(photo_description) + len("\n\nPlease focus your creative image generation on this Description: ")
                prompt = prompt[:max_length-additional_length]  # Ensure total prompt length is within the limit
                prompt += f"\n\nPlease focus your creative image generation on this Description: {photo_description}"

           # print(f"Sending to DALL-E API (Part {i+1}): {prompt}...")  # Debugging: Print first 100 characters of each prompt

            response = openai.Image.create(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size="1024x1024"
            )

            if response and response["data"]:
                image_url = response["data"][0]["url"]
                image_urls.append(image_url)
            else:
                print("No DALL·E image URL in the response.")
                image_urls.append(None)

        except Exception as e:
            print(f"Error generating DALL·E image URL: {str(e)}")
            traceback.print_exc()
            image_urls.append(None)

    return image_urls





# Route for the presentation generation page
@app.route('/')
def home():
    return render_template('generate_presentation.html')

# Route to handle PDF upload and presentation generation
# Route to handle PDF upload and presentation generation
# Route to handle PDF upload and presentation generation
# Route to handle PDF upload and presentation generation, including the DALL·E image
@app.route('/generate', methods=['POST'])
def generate():
    pdf_file_path = None
    try:
        # Handle PDF file upload
        pdf_file = request.files['pdf_file']
        pdf_file_path = save_pdf_file(pdf_file)
    except Exception as e:
        print(f"Error handling PDF file upload: {str(e)}")
        traceback.print_exc()
        return "Error handling PDF file upload."

    try:
        # Extract user inputs (keywords, question, and page_range)
        keywords = request.form.get('keywords')
        question = request.form.get('question')
        page_selection = request.form.get('page_selection', '')  # Get the page selection from the form

        # Extract text from the uploaded PDF for the specified page range
        extracted_text = extract_text_from_pdf(pdf_file_path, page_selection)

        #print(extracted_text)
    except Exception as e:
        print(f"Error extracting form data or text from PDF: {str(e)}")
        traceback.print_exc()
        return "Error extracting form data or text from PDF."

    try:
        # Generate presentation content with ChatGPT
        presentation_content = generate_presentation_content(extracted_text, keywords, question)
        if not presentation_content:
            raise ValueError("No content generated by ChatGPT.")
    except Exception as e:
        print(f"Error generating presentation content: {str(e)}")
        traceback.print_exc()
        return "Error generating presentation content."

    text_parts = split_text_into_parts(presentation_content)

    try:


        photo_description = request.form['photo_description']
        image_urls = generate_dalle_images_urls(text_parts, photo_description)
    except Exception as e:
        print(f"Error generating DALL·E image URL: {str(e)}")
        traceback.print_exc()
        return "Error generating DALL·E image URL."

    try:
        # Generate a PDF document with the presentation content and the DALL·E image
        pdf_buffer = generate_pdf_with_image(presentation_content, image_urls)
        if not pdf_buffer:
            raise ValueError("PDF buffer is empty.")

        # Send the PDF document as a response for download
        return Response(pdf_buffer, mimetype='application/pdf',
                        headers={'Content-Disposition': 'attachment; filename=fließText.pdf'})
    except Exception as e:
        print(f"Error sending PDF response: {str(e)}")
        traceback.print_exc()
        return "Error sending PDF response."


@app.route('/generate_pdf_with_image', methods=['POST'])
def generate_pdf_with_image_route():
    image_url = request.form['image_url']
    text = request.form['text']

    # Call the correct function to generate the PDF with the image and text
    pdf_content = generate_pdf_with_image(text, image_url)

    # Return the PDF content as a response for download
    if pdf_content:
        return Response(pdf_content, mimetype='application/pdf', headers={'Content-Disposition': 'attachment; filename=output.pdf'})
    else:
        return "Error generating PDF with image."


if __name__ == '__main__':
    app.run(debug=True)