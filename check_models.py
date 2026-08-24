import os
import json
import urllib.request

def check_models():
    api_key = ""
    with open("c:\\Users\\infomax\\OneDrive\\dev\\Daily news reporter creator\\daily-news-creator\\.env", "r") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                api_key = line.strip().split("=", 1)[1]
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
            for model in data.get("models", []):
                print(model.get("name"))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    check_models()
