import ezos
import openai

API_KEY = "YOUR_API_KEY_HERE" 
client = openai.OpenAI(
    api_key=API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

instructions = ezos.Jarvis(
    client,
    model="gemini-3.7-flash",
    instructions=[
        ezos.aiRead("You are a helpful PC assistant. Keep replies short."),
        ezos.aiRead("When user wants to open a app, use the this tool: ezos.open_app('app_name')"),
    ],
)

while True:
    user_input = input("Enter something ")

    reply = instructions.chat(user_input)
    print("AI", reply, "\n")

