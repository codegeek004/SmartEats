import os
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from PIL import Image
import pytesseract
from transformers import pipeline
import requests
import json
from authlib.integrations.flask_client import OAuth


app = Flask(__name__)
app.config['SECRET_KEY'] = 'lsjbgksjabgioh984y5837t5346873iuwb'
socketio = SocketIO(app, async_mode='eventlet')


classifier = pipeline("text-classification", model="facebook/bart-large-mnli")
qa_pipeline = pipeline("question-answering", model="deepset/roberta-base-squad2")
ner_pipeline = pipeline("ner", model="dbmdz/bert-large-cased-finetuned-conll03-english")


class ChatForm(FlaskForm):
	print('inside chatform')
	user_input = StringField("Ask about the product:", validators=[DataRequired()])
	submit = SubmitField("Send")

@app.route("/")
def home():
    return jsonify({"message": "Flask is running on Vercel!"})

def handler(event, context):
    return app(event, context)

@app.route("/chat")
def chat():
	form = ChatForm()
	return render_template("chat.html", form=form)

@app.route('/upload', methods=['POST'])
def upload():
    try:
        file = request.files.get("image")
        if not file:
            return jsonify({"error": "No image uploaded"}), 400

        extracted_text = extract_text(file.stream)  

        prompt_text = f"Given the following ingredients, is this product safe for a diabetic person?\n\n{extracted_text}"

        url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key=AIzaSyAEmTn2fafIXkteY2JdF811EMTcG01GZGI"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt_text}]}]}

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            return jsonify({"error": f"API Error: {response.text}"}), 500

        response_data = response.json()
        bot_response = response_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "No valid response.")
        print('response', bot_response)

        return jsonify({'extracted_text': extracted_text, 'response': bot_response})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@socketio.on("user_message")
def handle_message(data):
	print('inside handle_message')
	user_query = data["message"]
	context = session.get("product_text", "No product uploaded yet.")


	bot_response = ask_gemini(user_query, context)

	socketio.emit("bot_response", {"response": bot_response})

def extract_text(image_path):
	print('inside extracted_text')
	"""Extracts text from an image using Tesseract OCR."""
	try:
		print('in try')
		print("Processing image:", image_path)  # Debugging print
		img = Image.open(image_path)
		text = pytesseract.image_to_string(img).strip()
		print("Extracted text:", text)  # Debugging print
		return text
	except Exception as e:
		print('in exceptions')
		return f"Error processing image: {str(e)}"

def check_product_safety(text):
	print('inside check_product_safety')
	api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
	api_key = "AIzaSyAEmTn2fafIXkteY2JdF811EMTcG01GZGI"

	headers = {"Content-Type": "application/json"}
	payload = {
		"contents": [{"parts": [{"text": text}]}]  
	}

	try:
		print("in try")
		response = requests.post(f"{api_url}?key={api_key}", headers=headers, data=json.dumps(payload))
		response_data = response.json()

		print("Gemini API Response:", response_data)  

		if response.status_code == 200:
			return response_data.get("candidates", [{}])[0].get("content", "No valid response received.")
		else:
			return f"Error: {response_data.get('error', {}).get('message', 'Unknown error')}"
	except requests.exceptions.RequestException as e:
		print('error', e)
		return f"Error: {str(e)}"

def ask_gemini(question, context):
	print('inside ask_gemini')
	answer = qa_pipeline(question=question, context=context)
	return answer["answer"]

def extract_entities(text):
	print('extracted_entities')
	entities = ner_pipeline(text)
	extracted_ingredients = [entity['word'] for entity in entities if entity['entity'] == 'B-CHEMICAL']
	return extracted_ingredients

#initialize OAuth
oauth = OAuth(app)

#create a google oauth client
google = oauth.register(
		name = 'google',
		client_id = "",
		client_secret = "",
		server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
		client_kwargs={'scope': 'openid profile email',
                   'redirect_uri': 'http://127.0.0.1:5000/auth'},
	)


google_config_url = "https://accounts.google.com/.well-known/openid-configuration"
response = requests.get(google_config_url)
config = response.json()

@app.route('/login')
def login():
	redirect_uri = "http://127.0.0.1:5000/auth"
	return google.authorize_redirect(redirect_uri)

@app.route('/auth')
def auth():
	token = google.authorize_access_token()
	nonce = token.get('nonce')
	user = google.parse_id_token(token, nonce=nonce)
	session['user'] = user
	return redirect(url_for('chat'))
@app.route('/logout')
def logout():
	session.clear()
	return render_template('chat.html')


if __name__ == "__main__":
	app.run(debug=True)
	socketio.run(app, debug=True)
