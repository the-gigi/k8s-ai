"""A2A server interface for k8s-ai."""

import argparse
import sys
import os
import json
import secrets
from datetime import datetime

import uvicorn
from starlette.requests import Request
from starlette.responses import JSONResponse
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from .executor import K8sAgentExecutor


class ApiKeyManager:
    """Manages API keys for authentication."""
    
    def __init__(self, keys_file: str = 'keys.json'):
        self.keys_file = keys_file
        self.keys: dict[str, dict] = {}
        self.load_keys()
    
    def load_keys(self):
        """Load keys from JSON file."""
        if os.path.exists(self.keys_file):
            try:
                with open(self.keys_file, 'r') as f:
                    data = json.load(f)
                    self.keys = {key['key']: key for key in data.get('api_keys', [])}
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not load keys from {self.keys_file}: {e}")
                self.keys = {}
    
    def save_keys(self):
        """Save keys to JSON file."""
        try:
            data = {
                'api_keys': list(self.keys.values())
            }
            with open(self.keys_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving keys to {self.keys_file}: {e}")
    
    def generate_key(self, client_name: str = None) -> str:
        """Generate a new API key."""
        # Generate random suffix
        random_suffix = secrets.token_urlsafe(16)
        
        # Create key with client name if provided
        if client_name:
            safe_name = ''.join(c for c in client_name if c.isalnum() or c in '-_').lower()
            key = f"sk-k8sai-{safe_name}-{random_suffix}"
        else:
            key = f"sk-k8sai-{random_suffix}"
        
        # Store key metadata
        self.keys[key] = {
            'key': key,
            'name': client_name or 'Unnamed Client',
            'created': datetime.now().isoformat(),
            'last_used': None
        }
        
        self.save_keys()
        return key
    
    def validate_key(self, key: str) -> bool:
        """Validate an API key."""
        if key in self.keys:
            # Update last used timestamp
            self.keys[key]['last_used'] = datetime.now().isoformat()
            self.save_keys()
            return True
        return False
    
    def list_keys(self) -> list[dict]:
        """list all active keys."""
        return list(self.keys.values())
    
    def revoke_key(self, key: str) -> bool:
        """Revoke an API key."""
        if key in self.keys:
            del self.keys[key]
            self.save_keys()
            return True
        return False
    
    def add_single_key(self, key: str):
        """Add a single key (from --auth-key)."""
        self.keys[key] = {
            'key': key,
            'name': 'CLI Provided Key',
            'created': datetime.now().isoformat(),
            'last_used': None
        }


def create_auth_middleware(api_key_manager: ApiKeyManager):
    """Create authentication middleware."""
    async def auth_middleware(request: Request, call_next):
        # Skip auth for agent card endpoints
        if request.url.path in ["/.well-known/agent.json", "/.well-known/agent-card.json"]:
            return await call_next(request)
        
        # Check for authorization header
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            # Return proper A2A error format for better client error handling
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32002,
                        "message": "Authentication failed: Missing or invalid Authorization header. Expected 'Bearer <token>'",
                        "data": {"auth_error": True}
                    },
                    "id": None
                },
                status_code=401
            )
        
        # Extract and validate token
        token = auth_header[7:]  # Remove "Bearer " prefix
        if not api_key_manager.validate_key(token):
            # Return proper A2A error format for better client error handling
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32001,
                        "message": "Authentication failed: Invalid API key",
                        "data": {"auth_error": True}
                    },
                    "id": None
                },
                status_code=401
            )
        
        return await call_next(request)
    
    return auth_middleware


def main():
    """Main A2A server entry point."""
    parser = argparse.ArgumentParser(description='k8s-ai A2A Server')
    parser.add_argument('--context', '-c', required=True, help='Kubernetes context to use')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=9999, help='Port to bind to (default: 9999)')
    
    # Authentication arguments
    parser.add_argument('--auth-key', help='Single API key for authentication')
    parser.add_argument('--keys-file', default='keys.json', help='JSON file containing API keys (default: keys.json)')
    parser.add_argument('--generate-key', action='store_true', help='Generate a new API key')
    parser.add_argument('--client-name', help='Name for the client when generating a key')
    parser.add_argument('--list-keys', action='store_true', help='list all active API keys')
    parser.add_argument('--revoke-key', help='Revoke a specific API key')
    
    args = parser.parse_args()
    
    if not args.context:
        print("Error: Kubernetes context is required!")
        print("Usage: k8s-ai-server --context <kube context>")
        sys.exit(1)
    
    # Initialize API key manager
    api_key_manager = ApiKeyManager(args.keys_file)
    
    # Handle key management commands
    if args.generate_key:
        key = api_key_manager.generate_key(args.client_name)
        print(f"Generated API Key for '{args.client_name or 'Unnamed Client'}': {key}")
        print("Save this key - it won't be displayed again!")
        sys.exit(0)
    
    if args.list_keys:
        keys = api_key_manager.list_keys()
        if not keys:
            print("No API keys found.")
        else:
            print("Active API Keys:")
            for key_info in keys:
                last_used = key_info.get('last_used', 'Never')
                if last_used and last_used != 'Never':
                    last_used = last_used[:19]  # Show only date/time part
                print(f"  - {key_info['name']}: {key_info['key']} (created: {key_info['created'][:10]}, last used: {last_used})")
        sys.exit(0)
    
    if args.revoke_key:
        if api_key_manager.revoke_key(args.revoke_key):
            print(f"Revoked API key: {args.revoke_key}")
        else:
            print(f"API key not found: {args.revoke_key}")
        sys.exit(0)
    
    # Add single auth key if provided
    if args.auth_key:
        api_key_manager.add_single_key(args.auth_key)
    
    # Check if we have any keys configured for authentication
    use_auth = len(api_key_manager.keys) > 0 or args.auth_key
    if not use_auth:
        print("No authentication configured. Server will run without authentication!")
        print("Use --auth-key <key> or --generate-key to enable authentication.")
    else:
        print(f"Authentication enabled with {len(api_key_manager.keys)} API key(s)")
    
    # Check for environment-based auth keys
    env_keys = os.environ.get('K8S_AI_AUTH_KEYS')
    if env_keys:
        for key in env_keys.split(','):
            key = key.strip()
            if key:
                api_key_manager.add_single_key(key)
        print(f"Loaded {len(env_keys.split(','))} API key(s) from environment")
    
    # Define kubectl skill
    kubectl_skill = AgentSkill(
        id='kubectl_operations',
        name='Kubernetes Operations',
        description='Execute kubectl commands and provide Kubernetes cluster insights, troubleshooting, and management',
        tags=['kubernetes', 'kubectl', 'cluster', 'pods', 'deployments', 'services'],
        examples=[
            'show me all pods',
            'what is the status of the cluster?',
            'describe the nginx deployment', 
            'get service endpoints',
            'check node health',
            'troubleshoot pending pods'
        ]
    )
    
    # Create agent card with security schemes if auth is enabled
    security_schemes = None
    security = None

    if use_auth:
        # Define BearerAuth security scheme
        security_schemes = {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer'
            }
        }
        security = [{'BearerAuth': []}]

    agent_card = AgentCard(
        name='k8s-ai Agent',
        description=f'Kubernetes AI assistant with kubectl access for context: {args.context}',
        url=f'http://{args.host}:{args.port}/',
        version='1.0.0',
        default_input_modes=['text/plain'],
        default_output_modes=['text/plain'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[kubectl_skill],
        supports_authenticated_extended_card=True,
        security_schemes=security_schemes,
        security=security
    )
    
    # Set up request handler
    request_handler = DefaultRequestHandler(
        agent_executor=K8sAgentExecutor(context=args.context),
        task_store=InMemoryTaskStore(),
    )
    
    # Create and configure the A2A application
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )
    app = a2a_app.build()
    
    # Add authentication middleware if we have keys
    if use_auth:
        app.middleware("http")(create_auth_middleware(api_key_manager))
    
    print(f"Starting k8s-ai A2A server on {args.host}:{args.port}")
    print(f"Using Kubernetes context: {args.context}")
    print(f"Agent card available at: http://{args.host}:{args.port}/.well-known/agent.json")
    
    # Start the server
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
