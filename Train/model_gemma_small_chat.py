from ollama import chat

def call_gemma__small_chat(messages):
    return chat(model="gemma3:1b", messages=messages)
