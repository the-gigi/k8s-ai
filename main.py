import os
import sh
import json
from openai import OpenAI

client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
model_name = "gpt-4o"

tools = [
    {
        "type": "function",
        "function": {
            "name": "kubectl",
            "description": "execute a kubectl command against the current k8s cluster",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description":
                            """the kubectl command to execute (without kubectl, just 
                               the arguments). For example, 'get pods
                            '""",
                    },
                },
                "required": ["cmd"],
            },
        },
    }
]


def send(messages: list[dict[str, any]]) -> str:
    response = client.chat.completions.create(
        model=model_name, messages=messages, tools=tools, tool_choice="auto")
    r = response.choices[0].message
    if r.tool_calls:
        message = dict(
            role=r.role,
            content=r.content,
            tool_calls=[dict(id=t.id, type=t.type, function=dict(name=t.function.name, arguments=t.function.arguments)
                             ) for t in r.tool_calls if t.function])
        messages.append(message)
        for t in r.tool_calls:
            if t.function.name == 'kubectl':
                cmd = json.loads(t.function.arguments)['cmd'].split()
                result = sh.kubectl(cmd)
                messages.append(dict(tool_call_id=t.id, role="tool", name=t.function.name, content=result))
        return send(messages)
    return r.content.strip()


def main():
    print("Interactive Kubernetes Chat. Type 'exit' to quit.")
    messages = [{'role': 'system', 'content': 'You are a Kubernetes expert ready to help'}]
    while True:
        user_input = input("👤 You: ")
        if user_input.lower() == 'exit':
            break
        messages.append(dict(role="user", content=user_input))
        response = send(messages)
        print(f"🤖 AI: {response}\n----------")


if __name__ == "__main__":
    main()
