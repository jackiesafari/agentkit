from flask import Flask, request, Response
from agent import create_agent
from langchain.memory import ConversationBufferMemory
import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# Meta WhatsApp API Configuration
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
VERIFY_TOKEN = os.getenv('VERIFY_TOKEN')  # Add this for webhook verification
PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')
VERSION = os.getenv('VERSION', 'v17.0')  # Default to v17.0 if not specified

# Store user sessions
user_sessions = {}

def get_or_create_session(phone_number):
    if phone_number not in user_sessions:
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        agent = create_agent(memory)
        user_sessions[phone_number] = {
            'memory': memory,
            'agent': agent
        }
    return user_sessions[phone_number]

def send_whatsapp_message(recipient, message):
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": message}
    }
    
    response = requests.post(url, headers=headers, json=data)
    return response.json()

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    # Handle the verification request from Meta
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge
        return Response(status=403)

@app.route('/webhook', methods=['POST'])
async def webhook():
    data = request.get_json()
    
    if data['object'] == 'whatsapp_business_account':
        try:
            for entry in data['entry']:
                for change in entry['changes']:
                    if 'messages' in change['value']:
                        phone_number = change['value']['messages'][0]['from']
                        message = change['value']['messages'][0]['text']['body']
                        
                        # Get or create user session
                        session = get_or_create_session(phone_number)
                        agent = session['agent']
                        
                        # Get response from CDP agent
                        response = await agent.arun(message)
                        
                        # Send response back to WhatsApp
                        send_whatsapp_message(phone_number, response)
            
            return 'OK', 200
        except Exception as e:
            print(f"Error: {str(e)}")
            return 'Error', 500
    
    return 'Not a WhatsApp message', 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)