from ollama import chat

def call_llama_block(messages):
    return chat(model="mistral:latest", messages=messages)
