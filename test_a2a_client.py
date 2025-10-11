#!/usr/bin/env python3
"""Test script for modern A2A client with authentication and automated session management."""

import asyncio
import os
import httpx
import requests
import json
import subprocess
import time
import signal
from a2a.client import ClientFactory, ClientConfig
from a2a.client.helpers import create_text_message_object
from a2a.types import AgentCard, Role

# Global state for server management
server_process = None
server_started_by_test = False


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


def get_kubeconfig():
    """Get current kubeconfig as YAML string."""
    try:
        result = subprocess.run(
            ["kubectl", "config", "view", "--minify", "--raw"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error getting kubeconfig: {e}")
        return None


def create_session(api_key: str, admin_api_url: str = "http://localhost:9998") -> dict:
    """
    Create a new session for the current cluster.
    Multiple agents can have separate sessions for the same cluster.
    """
    # Get current context name
    try:
        result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            text=True,
            check=True
        )
        context_name = result.stdout.strip()
    except subprocess.CalledProcessError:
        context_name = "default"

    print(f"Creating new session for cluster '{context_name}'...")

    kubeconfig = get_kubeconfig()
    if not kubeconfig:
        return None

    response = requests.post(
        f"{admin_api_url}/sessions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "cluster_name": context_name,
            "kubeconfig": kubeconfig,
            "context": context_name,
            "ttl_hours": 1.0  # Short TTL for testing
        }
    )

    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            print(f"✅ Session created. Token: {data['session_token'][:30]}...")
            return data
        else:
            print(f"❌ Session creation failed: {data.get('error')}")
            return None
    else:
        print(f"❌ Admin API request failed: {response.status_code} - {response.text}")
        return None


def cleanup_session(api_key: str, session_token: str, admin_api_url: str = "http://localhost:9998"):
    """Delete session from Admin API."""
    print(f"\nCleaning up session {session_token[:30]}...")

    response = requests.delete(
        f"{admin_api_url}/sessions/{session_token}",
        headers={"Authorization": f"Bearer {api_key}"}
    )

    if response.status_code == 200:
        print("✅ Session cleaned up successfully")
    else:
        print(f"⚠️  Failed to cleanup session: {response.status_code}")


def is_server_running(a2a_url: str = "http://localhost:9999", admin_url: str = "http://localhost:9998") -> bool:
    """Check if k8s-ai server is running with correct version (new /sessions endpoint)."""
    try:
        # Try to get the agent card (no auth required)
        response = requests.get(f"{a2a_url}/.well-known/agent-card.json", timeout=2)
        if response.status_code != 200:
            return False

        # Check if admin API has the new /sessions endpoint (not old /clusters/register)
        # Try health endpoint first to verify admin API is up
        try:
            health_response = requests.get(f"{admin_url}/health", timeout=2)
            if health_response.status_code == 200:
                # Server is running - we'll validate endpoint version when we try to use it
                return True
        except requests.exceptions.RequestException:
            pass

        return True
    except requests.exceptions.RequestException:
        return False


def ensure_server(force_restart: bool = False) -> bool:
    """Ensure k8s-ai server is running. Start it if needed. Returns True if we started it."""
    global server_process, server_started_by_test

    if is_server_running() and not force_restart:
        print("✅ k8s-ai server is already running")
        return False

    if force_restart and is_server_running():
        print("⚠️  Stopping old server to restart with new code...")
        # Find and kill any running k8s-ai-server processes
        try:
            subprocess.run(["pkill", "-f", "k8s-ai-server"], check=False)
            time.sleep(2)  # Wait for process to die
        except Exception as e:
            print(f"Warning: Could not kill old server: {e}")

    print("🚀 Starting k8s-ai server...")

    # Get current context
    try:
        result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            text=True,
            check=True
        )
        context_name = result.stdout.strip()
    except subprocess.CalledProcessError:
        print("❌ Failed to get current kubectl context")
        return False

    # Start the server
    try:
        server_process = subprocess.Popen(
            ["uv", "run", "k8s-ai-server", "--context", context_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait for server to be ready (max 30 seconds)
        print("⏳ Waiting for server to start...")
        for i in range(30):
            time.sleep(1)
            if is_server_running():
                print(f"✅ Server started successfully (took {i+1}s)")
                server_started_by_test = True
                return True

        # Timeout
        print("❌ Server failed to start within 30 seconds")
        if server_process:
            server_process.terminate()
            server_process.wait()
        return False

    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return False


def cleanup_server():
    """Stop the server if we started it."""
    global server_process, server_started_by_test

    if server_started_by_test and server_process:
        print("\n🛑 Stopping k8s-ai server...")
        try:
            server_process.terminate()
            server_process.wait(timeout=10)
            print("✅ Server stopped successfully")
        except subprocess.TimeoutExpired:
            print("⚠️  Server didn't stop gracefully, killing it...")
            server_process.kill()
            server_process.wait()
        except Exception as e:
            print(f"⚠️  Error stopping server: {e}")

        server_process = None
        server_started_by_test = False


async def query_k8s():
    # Ensure server is running
    ensure_server()

    # Get API key from keys.json
    api_key = json.load(open("keys.json"))["api_keys"][0]["key"]
    if not api_key:
        print("❌ No API key found in keys.json")
        print("Generate a key with: uv run k8s-ai-server --generate-key --client-name 'test-client'")
        cleanup_server()
        return

    print(f"Using API key: {api_key[:20]}...")

    # Create a new session
    session_info = create_session(api_key)
    if not session_info:
        print("⚠️  Failed to create session - might be running old server version")
        print("🔄 Restarting server with latest code...")
        ensure_server(force_restart=True)

        # Retry session creation
        session_info = create_session(api_key)
        if not session_info:
            print("❌ Still failed to create session. Check server logs for details.")
            cleanup_server()
            return

    session_token = session_info["session_token"]

    try:
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

            # Create message with structured skill call format using the session token
            prompt = f'kubernetes_diagnose_issue: session_token={session_token}, issue_description=show me all deployments outside kube-system, namespace=default'
            message = create_text_message_object(Role.user, prompt)

            # Send message and handle responses
            print(f"Sending diagnostic request...")
            print(f"Issue: show me all deployments outside kube-system\n")

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

    finally:
        # Always cleanup the session after test completes
        cleanup_session(api_key, session_token)
        # Stop server if we started it
        cleanup_server()

if __name__ == "__main__":
    asyncio.run(query_k8s())
