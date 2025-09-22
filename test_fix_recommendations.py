#!/usr/bin/env python3
"""Test the kubernetes_fix_recommendations skill specifically."""

import asyncio
import json
import httpx
import re
from a2a.client import ClientFactory, ClientConfig
from a2a.client.helpers import create_text_message_object
from a2a.types import AgentCard, Role


def get_readonly_kubeconfig():
    """Get the read-only kubeconfig as YAML string."""
    try:
        with open('/Users/gigi/git/k8s-ai/holmesgpt-readonly-kubeconfig.yaml', 'r') as f:
            return f.read()
    except FileNotFoundError:
        print("⚠️  Read-only kubeconfig not found. Run './create_readonly_kubeconfig.sh' first.")
        return None


async def test_fix_recommendations():
    """Test kubernetes_fix_recommendations skill specifically."""
    print("🔧 Testing kubernetes_fix_recommendations skill")
    print("=" * 60)

    api_key = "test-key"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as http_client:
        # Register cluster
        print("🔒 Registering cluster...")
        readonly_kubeconfig = get_readonly_kubeconfig()
        if not readonly_kubeconfig:
            return

        register_data = {
            "cluster_name": "fix-recommendations-test",
            "kubeconfig": readonly_kubeconfig,
            "ttl_hours": 1
        }

        register_response = await http_client.post(
            "http://localhost:9998/clusters/register",
            json=register_data,
            headers=headers
        )

        if register_response.status_code != 200:
            print(f"❌ Cluster registration failed: {register_response.text}")
            return

        result = register_response.json()
        session_token = result.get('session_token')
        print(f"✅ Cluster registered, session token: {session_token[:25]}...")

        # Get agent card
        card_response = await http_client.get('http://localhost:9999/.well-known/agent-card.json')
        if card_response.status_code != 200:
            print(f"❌ Failed to get agent card: {card_response.status_code}")
            return

        card_data = card_response.json()

    # Create A2A client
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=30, headers=auth_headers) as a2a_client:
        config = ClientConfig(httpx_client=a2a_client)
        factory = ClientFactory(config)
        agent_card = AgentCard(**card_data)
        client = factory.create(agent_card)

        # Test fix recommendations skill
        print("\n🧠 Testing kubernetes_fix_recommendations skill")
        print("-" * 50)

        fix_prompt = f"kubernetes_fix_recommendations: session_token={session_token}, issue_type=pending_pods, namespace=default"
        message = create_text_message_object(Role.user, fix_prompt)

        print(f"Skill Call: {fix_prompt}")
        print("Waiting for response...")

        try:
            response_text = ""
            async for event in client.send_message(message):
                if hasattr(event, 'parts') and event.parts:
                    for part in event.parts:
                        if hasattr(part, 'root') and hasattr(part.root, 'text'):
                            response_text += part.root.text
                        elif hasattr(part, 'text'):
                            response_text += part.text

            print(f"\n✅ Fix Recommendations Response:")
            print("-" * 60)
            print(f"{response_text}")
            print("-" * 60)

            # Try to parse JSON from the response
            try:
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    parsed_data = json.loads(json_str)

                    print(f"\n📊 Parsed Fix Recommendations:")
                    if 'fix_recommendations' in parsed_data:
                        recommendations = parsed_data['fix_recommendations']
                        print(f"   • Total Recommendations: {len(recommendations)}")

                        for i, rec in enumerate(recommendations, 1):
                            print(f"\n   {i}. {rec.get('issue', 'Unknown Issue')} ({rec.get('severity', 'unknown')} severity)")
                            print(f"      Description: {rec.get('description', 'No description')}")

                            if 'root_causes' in rec:
                                print(f"      Root Causes: {len(rec['root_causes'])} identified")
                                for cause in rec['root_causes'][:2]:  # Show first 2
                                    print(f"        - {cause}")

                            if 'detailed_analysis' in rec:
                                analysis = rec['detailed_analysis']
                                print(f"      Pod Analysis: {len(analysis)} pods analyzed in detail")

                            if 'kubectl_commands' in rec:
                                commands = rec['kubectl_commands']
                                print(f"      kubectl Commands: {len(commands)} diagnostic commands")
                                for cmd in commands[:2]:  # Show first 2
                                    print(f"        - {cmd}")

                    if 'preventive_measures' in parsed_data:
                        measures = parsed_data['preventive_measures']
                        print(f"\n   🛡️ Preventive Measures: {len(measures)} categories")
                        for measure in measures:
                            category = measure.get('category', 'Unknown')
                            recs = measure.get('recommendations', [])
                            print(f"      - {category}: {len(recs)} recommendations")

            except Exception as parse_error:
                print(f"⚠️  Could not parse JSON structure: {parse_error}")

        except Exception as e:
            print(f"❌ Fix recommendations skill failed: {e}")
            return

    print(f"\n🎉 Fix Recommendations Test Completed!")


if __name__ == "__main__":
    asyncio.run(test_fix_recommendations())