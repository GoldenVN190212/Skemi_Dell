from ollama import chat

def call_gemma_block(messages):
    return chat(model="gemma3:1b", messages=messages)
