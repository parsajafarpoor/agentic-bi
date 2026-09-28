import requests


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "deepseek-r1:7b"


def ask_deepseek(question: str) -> str:

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ],
        "stream": False
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=600
    )

    response.raise_for_status()

    data = response.json()

    return data["message"]["content"]


if __name__ == "__main__":

    question = "فقط در یک جمله بگو چرا تحلیل داده برای شرکت‌ها مهم است."

    answer = ask_deepseek(question)

    print("\nDeepSeek:")
    print(answer)