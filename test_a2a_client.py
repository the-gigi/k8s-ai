#!/usr/bin/env python3
"""Test script for modern A2A client with authentication."""

import asyncio
import os
import httpx
import requests
import json
from a2a.client import ClientFactory, ClientConfig
from a2a.client.helpers import create_text_message_object
from a2a.types import AgentCard, Role


class AuthInterceptorClient(httpx.AsyncClient):
    """Custom httpx client that intercepts 401 responses and converts them to proper errors."""
    
    async def send(self, request, **kwargs):
        response = await super().send(request, **kwargs)
        
        # Intercept 401 authentication errors
        if response.status_code == 401:
            try:
                # Read the response content
                content = await response.aread()
                error_data = json.loads(content)
                
                # Check if it's our JSON-RPC error format
                if "jsonrpc" in error_data and "error" in error_data:
                    auth_error = error_data["error"]["message"]
                else:
                    # Handle simple JSON error format
                    auth_error = error_data.get("error", "Authentication failed")
                
                # Create a new response with proper error message for the client
                error_response = httpx.Response(
                    status_code=401,
                    headers={"content-type": "application/json"},
                    content=json.dumps({
                        "error": f"Authentication Error: {auth_error}"
                    }).encode(),
                    request=request
                )
                return error_response
                
            except (json.JSONDecodeError, Exception):
                # If we can't parse JSON, create simple error response
                error_response = httpx.Response(
                    status_code=401,
                    headers={"content-type": "application/json"},
                    content=json.dumps({
                        "error": "Authentication Error: Invalid API key"
                    }).encode(),
                    request=request
                )
                return error_response
        
        return response

async def query_k8s():
    # Get API key from environment or use default for testing
    api_key = os.environ.get('K8S_AI_API_KEY')
    if not api_key:
        print("No API key provided. Set K8S_AI_API_KEY environment variable.")
        print("For testing, you can generate a key with: k8s-ai-server --generate-key --client-name 'test-client'")
        return
    
    # Get agent card (no auth required)
    card_response = requests.get('http://localhost:9999/.well-known/agent-card.json')
    card_data = card_response.json()
    
    # Create config and client with authentication using our custom interceptor
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    async with AuthInterceptorClient(timeout=30, headers=auth_headers) as http_client:
        config = ClientConfig(httpx_client=http_client)
        factory = ClientFactory(config)
        
        # Create agent card object  
        agent_card = AgentCard(**card_data)
        
        # Create client
        client = factory.create(agent_card)
        
        # Create message
        prompt = 'show me all the deployments outside kube-system'
        message = create_text_message_object(Role.user, prompt)
        
        # Send message and handle responses
        print(f"Using API key: {api_key[:20]}...")
        print(f"Sending message: '{prompt}'")
        
        try:
            async for event in client.send_message(message):
                if hasattr(event, 'parts') and event.parts:
                    for part in event.parts:
                        if hasattr(part, 'root') and hasattr(part.root, 'text'):
                            print("Response:", part.root.text)
                        elif hasattr(part, 'text'):
                            print("Response:", part.text)
        except httpx.HTTPStatusError as e:
            if "Authentication Error" in str(e):
                print(f"Auth Error: {e}")
            else:
                print(f"HTTP Error: {e}")
        except Exception as e:
            # Check if this is the misleading SSE error that's actually an auth issue
            error_msg = str(e)
            if ("Invalid SSE response" in error_msg and 
                "Expected response header Content-Type to contain 'text/event-stream', got 'application/json'" in error_msg):
                
                # Make a quick test request to check if it's actually a 401 auth error
                try:
                    test_response = requests.post('http://localhost:9999/', 
                                                headers={"Authorization": f"Bearer {api_key}",
                                                        "Content-Type": "application/json"},
                                                json={"jsonrpc": "2.0", "id": "auth-test", "method": "message/send",
                                                     "params": {"message": {"role": "user", "message_id": "test", 
                                                               "parts": [{"kind": "text", "text": "test"}]}}})
                    
                    if test_response.status_code == 401:
                        # It's actually an auth error
                        try:
                            error_data = test_response.json()
                            if "jsonrpc" in error_data and "error" in error_data:
                                auth_error = error_data["error"]["message"]
                            else:
                                auth_error = error_data.get("error", "Invalid API key")
                            print(f"Auth Error: {auth_error}")
                        except:
                            print("Auth Error: Invalid API key")
                    else:
                        # It's a real SSE error, not auth
                        print(f"SSE Protocol Error: {e}")
                        
                except requests.RequestException:
                    # Can't test, fall back to original error
                    print(f"Error: {e}")
            else:
                print(f"Error: {e}")
                if "401" in str(e):
                    print("This might be an authentication issue. Check your API key.")

if __name__ == "__main__":
    asyncio.run(query_k8s())
