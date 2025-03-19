#!/usr/bin/env python3

import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from PIL import Image, ImageDraw, ImageFont
import qrcode
from datetime import datetime
import requests
import logging
import re

# Configuration
MIN_CARDS = 1
MAX_CARDS = 12
LOGO_FILENAME = "static/logo.png"
FONT_PATH = "static/arial.ttf"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "card_generator.log")
GENERATED_DIR = os.path.join('static', 'generated_cards')
os.makedirs(GENERATED_DIR, exist_ok=True)

# Ensure directories exist
os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = '3466'  # Replace with a secure key in production

# Set up logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
					format="%(asctime)s:%(levelname)s:%(message)s")

# Global variables to store last generated info
last_generated = {
	'filename': None,
	'timestamp': None
}

@app.route('/')
def index():
	return render_template('index.html')

@app.route('/generate_password')
def generate_password_route():
	"""
	Generates a password using an online service.
	"""
	strong = request.args.get('strong', 'false').lower() == 'true'
	url = "http://www.dinopass.com/password/simple"
	if strong:
		url = "http://www.dinopass.com/password/strong"
	try:
		response = requests.get(url)
		if response.status_code == 200:
			password = response.text.strip()
			return password
		else:
			return "Error generating password.", 500
	except requests.RequestException as e:
		logging.error(f"Password generation failed: {str(e)}")
		return "Error generating password.", 500
	
@app.route('/generate', methods=['POST'])
def generate():
	mode = request.form.get('mode')
	num_cards = int(request.form.get('num_cards'))
	
	if not (MIN_CARDS <= num_cards <= MAX_CARDS):
		flash(f"Please select a number of cards between {MIN_CARDS} and {MAX_CARDS}.")
		return redirect(url_for('index'))
	
	try:
		if mode == "WiFi":
			ssids = request.form.get('ssid').strip().split('\n')[:num_cards]
			passwords = request.form.get('password').strip().split('\n')[:num_cards]
			if len(ssids) < num_cards or len(passwords) < num_cards:
				flash("Not enough SSIDs or passwords provided.")
				return redirect(url_for('index'))
			generate_wifi_cards(num_cards, ssids, passwords)
		else:
			names = request.form.get('name').strip().split('\n')[:num_cards]
			phone_numbers = request.form.get('phone_number').strip().split('\n')[:num_cards]
			if len(names) < num_cards or len(phone_numbers) < num_cards:
				flash("Not enough names or phone numbers provided.")
				return redirect(url_for('index'))
			generate_customer_cards(num_cards, names, phone_numbers)
			
		flash(f"{num_cards} customer cards generated successfully.")
		return redirect(url_for('result'))
	except ValueError:
		flash("Invalid input. Please ensure all fields are correctly filled.")
		return redirect(url_for('index'))
	except Exception as e:
		logging.error(f"Unexpected error during card generation: {str(e)}")
		flash("An unexpected error occurred. Please check the logs for details.")
		return redirect(url_for('index'))
	
@app.route('/result')
def result():
	if last_generated['filename']:
		return render_template('result.html', generated_image=f"generated_cards/{last_generated['filename']}")
	else:
		flash("No cards have been generated yet.")
		return redirect(url_for('index'))
	
@app.route('/last')
def last():
	if last_generated['filename']:
		return render_template('last.html',
								filename=f"generated_cards/{last_generated['filename']}",
								timestamp=last_generated['timestamp'].strftime("%Y-%m-%d %H:%M:%S"))
	else:
		return render_template('last.html', filename=None, timestamp=None)
	
@app.route('/static/<path:filename>')
def download_file(filename):
	return send_from_directory(GENERATED_DIR, filename, as_attachment=True)

def calculate_multiline_textsize(draw, text, font, spacing):
	"""
	Calculates the size of multiline text.

	Parameters:
	- draw: ImageDraw object.
	- text: Text to be measured.
	- font: Font used for the text.
	- spacing: Spacing between lines.

	Returns:
	- max_width: Maximum width of the text.
	- total_height: Total height of the text.
	"""
	lines = text.split('\n')
	max_width = max(draw.textbbox((0, 0), line, font=font)[2] - draw.textbbox((0, 0), line, font=font)[0] for line in lines)
	total_height = sum(draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] + spacing for line in lines) - spacing
	return max_width, total_height

def generate_wifi_credentials(ssid, password):
	"""
	Generates WiFi credentials with minimum password length check.

	Parameters:
	- ssid: SSID.
	- password: Password.

	Returns:
	- ssid: SSID.
	- password: Password.
	"""
	if len(password) < 8:
		password += "0" * (8 - len(password))
	return ssid, password

def sanitize_text(text):
	"""
	Removes any non-printable or unsupported characters from the input text.

	Parameters:
	- text: The text to be sanitized.

	Returns:
	- sanitized text.
	"""
	# Remove any non-printable characters
	text = ''.join(filter(lambda x: x.isprintable(), text))
	
	# Optional: you can also remove any specific symbols that might be causing the issue
	text = re.sub(r'[^\w\s\.\-@#]+', '', text)
	
	return text

def generate_wifi_cards(num_cards, ssids, passwords):
	"""
	Generates WiFi cards with QR codes.
	"""
	num_cols = 3
	num_rows = (num_cards + num_cols - 1) // num_cols
	
	# Card dimensions
	card_aspect_ratio = 2
	total_width = 1600
	card_width = total_width // num_cols
	card_height = card_width // card_aspect_ratio
	text_spacing = 12.5
	qr_spacing = 40
	border_size = 20
	total_height = num_rows * (card_height + border_size)
	
	img = Image.new('RGB', (total_width, total_height), color=(255, 255, 255))
	draw = ImageDraw.Draw(img)
	
	logo_img = Image.open(LOGO_FILENAME)
	logo_height = card_height // 5
	logo_width = int(logo_img.width * (logo_height / logo_img.height))
	logo_img = logo_img.resize((logo_width, logo_height))
	
	card_index = 0
	
	for ssid, password in zip(ssids, passwords):
		# Sanitize SSID and password
		ssid = sanitize_text(ssid)
		password = sanitize_text(password)
		
		ssid, password = generate_wifi_credentials(ssid, password)
		
		row = card_index // num_cols
		col = card_index % num_cols
		card_x = col * (card_width + border_size)
		card_y = row * (card_height + border_size)
		
		draw.rectangle([card_x, card_y, card_x + card_width, card_y + card_height], outline="black")
		
		logo_x = card_x + (card_width - logo_img.width) // 2
		logo_y = card_y + 20
		img.paste(logo_img, (logo_x, logo_y), mask=logo_img)
		
		max_font_size = 30
		font = ImageFont.truetype(FONT_PATH, max_font_size)
		
		text = f"SSID: {ssid}\nPassword: {password}"
		text_width, text_height = calculate_multiline_textsize(draw, text, font, text_spacing)
		while text_width > card_width - 2 * text_spacing or text_height > card_height - 2 * text_spacing:
			max_font_size -= 1
			font = ImageFont.truetype(FONT_PATH, max_font_size)
			text_width, text_height = calculate_multiline_textsize(draw, text, font, text_spacing)
			
		text_x = card_x + (card_width - text_width) // 2
		text_y = card_y + (card_height - text_height) // 2 - text_height // 2
		draw.multiline_text((text_x, text_y), text, fill=(0, 0, 0), font=font, align="center", spacing=text_spacing)
		
		qr = qrcode.QRCode(
			version=1,
			error_correction=qrcode.constants.ERROR_CORRECT_L,
			box_size=4,
			border=0,
		)
		qr.add_data(f"WIFI:T:WPA;S:{ssid};P:{password};;")
		qr.make(fit=True)
		
		qr_img = qr.make_image(fill_color="black")
		fixed_qr_size = (110, 110)
		qr_img = qr_img.resize(fixed_qr_size)
		
		qr_x = int(card_x + (card_width - fixed_qr_size[0]) // 2)
		qr_y = int(card_y + (card_height - fixed_qr_size[1]) // 2 + text_height // 2 + text_spacing + qr_spacing)
		
		if qr_y + qr_img.height > card_y + card_height:
			qr_y = card_y + card_height - qr_img.height
			
		img.paste(qr_img, (qr_x, qr_y))
		
		card_index += 1
		
	save_image(img, num_cards, "WiFi")
	
def generate_customer_cards(num_cards, names, phone_numbers):
	"""
	Generates customer cards with names and phone numbers.
	"""
	num_cols = 3
	num_rows = (num_cards + num_cols - 1) // num_cols
	
	# Card dimensions
	card_aspect_ratio = 2
	total_width = 1600
	card_width = total_width // num_cols
	card_height = card_width // card_aspect_ratio
	text_spacing = 12.5
	border_size = 20
	total_height = num_rows * (card_height + border_size)
	
	img = Image.new('RGB', (total_width, total_height), color=(255, 255, 255))
	draw = ImageDraw.Draw(img)
	
	logo_img = Image.open(LOGO_FILENAME)
	logo_height = card_height // 5
	logo_width = int(logo_img.width * (logo_height / logo_img.height))
	logo_img = logo_img.resize((logo_width, logo_height))
	
	card_index = 0
	
	for name, phone_number in zip(names, phone_numbers):
		row = card_index // num_cols
		col = card_index % num_cols
		card_x = col * (card_width + border_size)
		card_y = row * (card_height + border_size)
		
		draw.rectangle([card_x, card_y, card_x + card_width, card_y + card_height], outline="black")
		
		logo_x = card_x + (card_width - logo_img.width) // 2
		logo_y = card_y + 20
		img.paste(logo_img, (logo_x, logo_y), mask=logo_img)
		
		max_font_size = 40
		font = ImageFont.truetype(FONT_PATH, max_font_size)
		
		text = f"Name: {name}\nPhone: {phone_number}"
		text_width, text_height = calculate_multiline_textsize(draw, text, font, text_spacing)
		while text_width > card_width - 2 * text_spacing or text_height > card_height - 2 * text_spacing:
			max_font_size -= 1
			font = ImageFont.truetype(FONT_PATH, max_font_size)
			text_width, text_height = calculate_multiline_textsize(draw, text, font, text_spacing)
			
		text_x = card_x + (card_width - text_width) // 2
		text_y = card_y + (card_height - text_height) // 2
		draw.multiline_text((text_x, text_y), text, fill=(0, 0, 0), font=font, align="center", spacing=text_spacing)
		
		card_index += 1
		
	save_image(img, num_cards, "Phone")
	
def save_image(img, num_cards, card_type):
	"""
	Saves the generated image and logs the event.

	Parameters:
	- img: Image to save.
	- num_cards: Number of cards generated.
	- card_type: Type of card ('WiFi' or 'Phone').
	"""
	global last_generated
	timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
	filename = f"cards_{card_type}_{num_cards}_{timestamp}.png"
	filepath = os.path.join(GENERATED_DIR, filename)
	img.save(filepath)
	last_generated['filename'] = filename
	last_generated['timestamp'] = datetime.now()
	logging.info(f"Generated {num_cards} {card_type} cards and saved to {filename}")
	
if __name__ == '__main__':
	app.run(debug=True)
	
