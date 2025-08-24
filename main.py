import argparse
import json
import os
import sys

import sh
from openai import OpenAI

client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
model_name = "gpt-4o"
tools = [{
    "type": "function",
    "function": {
        "name": "kubectl",
        "description": "execute a kubectl command against the current k8s cluster",
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {
                    "type": "string",
                    "description": (
                        "the kubectl command to execute (without kubectl, just "
                        "the arguments). For example, 'get pods'"
                    ),
                },
            },
            "required": ["cmd"],
        },
    },
}]

k8s_context = None


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
                if k8s_context:
                    cmd = ['--context', k8s_context] + cmd
                result = sh.kubectl(cmd)
                messages.append(dict(tool_call_id=t.id, role="tool", name=t.function.name, content=result))
        return send(messages)
    return r.content.strip()


def main():
    global k8s_context
    
    parser = argparse.ArgumentParser(description='Interactive Kubernetes Chat')
    parser.add_argument('--context', '-c', help='Kubernetes context to use')
    args = parser.parse_args()
    
    k8s_context = args.context
    
    if not k8s_context:
        print("Error: Kubernetes context is required!")
        print("Usage: python main.py --context <kube context>")
        sys.exit(1)

    msg = f"☸️ Interactive Kubernetes Chat (using context: {k8s_context}). Type 'exit' to quit."
    print(f"{msg}\n{'-' * len(msg)}")
    messages = [{'role': 'system', 'content': 'You are a Kubernetes expert ready to help'}]
    while (user_input := input("👤 You: ")).lower() != 'exit':
        messages.append(dict(role="user", content=user_input))
        response = send(messages)
        print(f"🤖 AI: {response}\n----------")


if __name__ == "__main__":
    main()
