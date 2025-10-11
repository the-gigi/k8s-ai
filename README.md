# k8s-ai

Kubernetes AI assistant with kubectl access. You can run it as an interactive CLI chatbot or as an [A2A (Agent-to-Agent)](https://a2a-protocol.org/) server to interact with your Kubernetes clusters in natural language.

## Features

- 🤖 **Interactive CLI**: Chat directly with your Kubernetes clusters
- 🌐 **A2A Server**: Expose kubectl capabilities as an A2A agent for other AI systems
- ⚡ **Smart kubectl execution**: Automatically runs kubectl commands based on natural language requests
- 🔧 **Context-aware**: Works with any Kubernetes context

# Setup

## Install dependencies with uv

```shell
uv sync
```

# Usage

## CLI Mode (Interactive Chat)

Run as an interactive command-line tool:

```shell
# Using uv
uv run k8s-ai-cli --context <your-kube-context>

# Or using the old main.py for backward compatibility
uv run python main.py --context <your-kube-context>
```

Example with a kind cluster:
```shell
uv run k8s-ai-cli --context kind-k8s-ai
```

## A2A Server Mode

Run as an A2A server to expose kubectl capabilities to other AI agents:

```shell
# Recommended: Session-based access (no --context needed)
uv run k8s-ai-server [--host 0.0.0.0] [--port 9999]

# Legacy: With default context (deprecated)
uv run k8s-ai-server --context <your-kube-context>
```

**Modern approach:** Clients create sessions via Admin API (see below) instead of relying on server's default context.

Example:
```shell
# Start A2A server with session-based access (recommended)
uv run k8s-ai-server

# Start with default context (legacy mode)
uv run k8s-ai-server --context kind-k8s-ai

# Start on custom host/port
uv run k8s-ai-server --host localhost --port 8080
```

### 🔐 Authentication

The A2A server supports API key authentication for secure access:

#### Generate API Keys
```shell
# Generate a new API key for a client
uv run k8s-ai-server --generate-key --client-name "dashboard-client"
# Output: 🔑 Generated API Key for 'dashboard-client': sk-k8sai-dashboard-abc123xyz

# Generate key without client name
uv run k8s-ai-server --generate-key
```

#### Manage API Keys
```shell
# List all active API keys
uv run k8s-ai-server --list-keys

# Revoke a specific API key
uv run k8s-ai-server --revoke-key sk-k8sai-dashboard-abc123xyz
```

#### Start Server with Authentication
```shell
# Server with generated keys (reads from keys.json)
uv run k8s-ai-server

# Server with single API key
uv run k8s-ai-server --auth-key "my-secret-key"

# Server with environment variable
export K8S_AI_AUTH_KEYS="key1,key2,key3"
uv run k8s-ai-server

# Custom keys file location
uv run k8s-ai-server --keys-file /path/to/my-keys.json
```

#### Server Output Examples

**Without Authentication:**
```
🚀 Starting k8s-ai A2A server on 0.0.0.0:9999
☸️ Using Kubernetes context: kind-k8s-ai
⚠️  No authentication configured. Server will run without authentication!
   Use --auth-key <key> or --generate-key to enable authentication.
🌐 Agent card available at: http://0.0.0.0:9999/.well-known/agent.json
```

**With Authentication (Session-based):**
```
Authentication enabled with 4 API key(s)
Starting k8s-ai A2A Diagnostic Server...
  • A2A Protocol Server: http://0.0.0.0:9999/
  • Admin API Server: http://0.0.0.0:9998/
  • Using session-based cluster management
  • Agent card: http://0.0.0.0:9999/.well-known/agent.json
INFO:     Uvicorn running on http://0.0.0.0:9998 (Press CTRL+C to quit)
INFO:     Uvicorn running on http://0.0.0.0:9999 (Press CTRL+C to quit)
```

**With Authentication (Legacy mode with --context):**
```
Authentication enabled with 4 API key(s)
Starting k8s-ai A2A Diagnostic Server...
  • A2A Protocol Server: http://0.0.0.0:9999/
  • Admin API Server: http://0.0.0.0:9998/
  • Default Kubernetes context: kind-k8s-ai (deprecated)
  • Agent card: http://0.0.0.0:9999/.well-known/agent.json
```

**Note**: Two servers start - A2A Protocol (9999) and Admin API (9998). Both log their startup, which is normal behavior.

**Key Generation:**
```
🔑 Generated API Key for 'dashboard-client': sk-k8sai-dashboard-FkL9mN2pQ3rS
⚠️  Save this key - it won't be displayed again!
```

### A2A Server Features

- **Agent Card**: Available at `/.well-known/agent.json` (no authentication required)
- **API Key Authentication**: Secure access with Bearer token authentication
- **Multi-Client Support**: Generate unique API keys for different clients
- **Key Management**: Generate, list, and revoke API keys via CLI
- **Kubectl Operations**: Execute kubectl commands via A2A protocol
- **Streaming Support**: Real-time response streaming
- **Context Isolation**: Each server instance works with a specific Kubernetes context
- **Flexible Configuration**: Support for single keys, key files, and environment variables

### Admin API (Port 9998)

When running the A2A server, an **admin API** is automatically started on port 9998 (configurable with `--admin-port`). This API enables **session-based cluster access** - clients provide their kubeconfig to create temporary sessions.

#### Admin API Endpoints

**POST `/sessions`** - Create a new cluster session
```bash
curl -X POST http://localhost:9998/sessions \
  -H "Authorization: Bearer $A2A_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "production-east",
    "kubeconfig": "<full kubeconfig YAML>",
    "ttl_hours": 24.0
  }'

# Returns:
{
  "success": true,
  "session_token": "k8s-ai-session-abc123...",
  "cluster_name": "production-east",
  "api_server": "https://prod-east.example.com:6443",
  "namespace": "default",
  "connectivity_status": "connected",
  "expires_at": "2024-10-12T10:00:00Z"
}
```

**GET `/sessions`** - List all active sessions (admin only)
```bash
curl http://localhost:9998/sessions \
  -H "Authorization: Bearer $A2A_API_KEY"

# Returns:
{
  "total_sessions": 2,
  "sessions": [
    {
      "session_token": "k8s-ai-session-abc123...",
      "cluster_name": "production-east",
      "expires_at": "2024-10-12T10:00:00Z"
    },
    ...
  ]
}
```

**GET `/sessions/mine`** - List only your sessions
```bash
curl http://localhost:9998/sessions/mine \
  -H "Authorization: Bearer $A2A_API_KEY"
```

**DELETE `/sessions/{session_token}`** - Delete a session
```bash
curl -X DELETE http://localhost:9998/sessions/k8s-ai-session-abc123... \
  -H "Authorization: Bearer $A2A_API_KEY"
```

#### Creating Sessions from Client Code

```python
import httpx
import subprocess

# Create a cluster session
async with httpx.AsyncClient() as client:
    # Get kubeconfig from your local kubectl config
    kubeconfig = subprocess.check_output(
        ["kubectl", "config", "view", "--context=prod-cluster", "--minify", "--raw"],
        text=True
    )

    # Create session via Admin API
    response = await client.post(
        "http://localhost:9998/sessions",
        headers={"Authorization": f"Bearer {admin_api_key}"},
        json={
            "cluster_name": "prod-cluster",
            "kubeconfig": kubeconfig,
            "ttl_hours": 24.0
        }
    )

    # Get session token for A2A operations
    session_token = response.json()["session_token"]

    # Use session_token in A2A skill calls
    skill_call = f"kubernetes_diagnose_issue: session_token={session_token}, issue_description=..."

    # Clean up session when done
    await client.delete(
        f"http://localhost:9998/sessions/{session_token}",
        headers={"Authorization": f"Bearer {admin_api_key}"}
    )
```

**How Sessions Work:**
- **Client provides kubeconfig**: You send your cluster credentials to the server
- **Temporary storage**: Server stores credentials in memory with TTL
- **Multiple sessions per cluster**: Different agents can have separate sessions for the same cluster
- **Client-scoped**: Each session is tied to the API key that created it
- **Auto-expiration**: Sessions automatically expire after TTL

### A2A Client Example

#### Authenticated Client Usage

```bash
# Set your API key (get this from server key generation)
export K8S_AI_API_KEY="sk-k8sai-dashboard-abc123xyz"

# Test with the included script
uv run python test_a2a_client.py
```

#### Using A2A Python Client
```python
import os
import httpx
from a2a.client import ClientFactory, ClientConfig
from a2a.client.helpers import create_text_message_object
from a2a.types import Role

# Set up authentication
api_key = os.environ.get('K8S_AI_API_KEY')
auth_headers = {"Authorization": f"Bearer {api_key}"}

# Create authenticated client
async with httpx.AsyncClient(headers=auth_headers) as http_client:
    config = ClientConfig(httpx_client=http_client)
    factory = ClientFactory(config)
    client = factory.create(agent_card)
    
    message = create_text_message_object(Role.user, 'show me all pods')
    async for event in client.send_message(message):
        # Handle response events
        pass
```

#### Direct HTTP Requests (JSON-RPC)
```python
import requests
import json

# Include authentication header
headers = {
    "Authorization": "Bearer sk-k8sai-dashboard-abc123xyz",
    "Content-Type": "application/json"
}

payload = {
    "jsonrpc": "2.0",
    "id": "test-1", 
    "method": "message/send",
    "params": {
        "message": {
            "role": "user",
            "message_id": "msg-1",
            "parts": [{"kind": "text", "text": "show me all pods"}]
        }
    }
}

response = requests.post('http://localhost:9999/', 
                        json=payload, 
                        headers=headers).json()
print(response['result']['parts'][0]['text'])
```

Example output:
```
Here are the current pods in the cluster:

1. **some-app-65696dbff4-kxwvf**: 
   - Ready: 0/1
   - Status: Pending
   - Restarts: 0
   - Age: 108 minutes

2. **some-app-65696dbff4-mj44r**:
   - Ready: 0/1
   - Status: Pending
   - Restarts: 0
   - Age: 108 minutes

3. **some-app-65696dbff4-qjc6l**:
   - Ready: 0/1
   - Status: Pending
   - Restarts: 0
   - Age: 108 minutes
```

# k8s-ai in Action

Let's create a kind cluster first

```
❯ kind create cluster -n k8s-ai
Creating cluster "k8s-ai" ...
 ✓ Ensuring node image (kindest/node:v1.33.1) 🖼
 ✓ Preparing nodes 📦
 ✓ Writing configuration 📜
 ✓ Starting control-plane 🕹️
 ✓ Installing CNI 🔌
 ✓ Installing StorageClass 💾
Set kubectl context to "kind-k8s-ai"
You can now use your cluster with:

kubectl cluster-info --context kind-k8s-ai

Have a nice day! 👋
```

Now, let's cause some trouble in the cluster. Here is a deployment that will never be ready because it requires its pods
to be scheduled on a node with a label that doesn't exist in the cluster:

```shell
echo '
apiVersion: apps/v1
kind: Deployment
metadata:
  name: some-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: some-app
  template:
    metadata:
      labels:
        app: some-app
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: no-such-node
                    operator: In
                    values:
                      - "true"
      containers:
        - name: pause
          image: registry.k8s.io/pause:3.9
' | kubectl apply -f - 

deployment.apps/some-app created
```

Let's confirm that all the pods were created, but none of them are running:

```shell
❯ kubectl get po
NAME                        READY   STATUS    RESTARTS   AGE
some-app-55cb6c5586-25gcj   0/1     Pending   0          117s
some-app-55cb6c5586-6xg2x   0/1     Pending   0          15s
some-app-55cb6c5586-b4sc7   0/1     Pending   0          15s
```

Alright, let's cause more havoc and create a deployment for Nginx with an invalid image name:

```shell
echo '
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
        - name: nginx
          image: nnnnnnnnginx
' | kubectl apply -f -

deployment.apps/nginx created
```

Let's check the status of our cluster now:

```shell
❯ kubectl get po
NAME                        READY   STATUS         RESTARTS   AGE
nginx-74f5dd8d8f-zfdmw      0/1     ErrImagePull   0          34s
some-app-55cb6c5586-25gcj   0/1     Pending        0          9m3s
some-app-55cb6c5586-6xg2x   0/1     Pending        0          7m21s
some-app-55cb6c5586-b4sc7   0/1     Pending        0          7m21s
```

So, we have two deployments, one of them has Three pending pods and the other one is in error state. Let's ask k8s-ai to
help us:

```shell
❯ uv run k8s-ai-cli --context kind-k8s-ai
☸️ Interactive Kubernetes Chat (using context: kind-k8s-ai). Type 'exit' to quit.
---------------------------------------------------------------------------------
👤 You: what's the cluster's status?
🤖 AI: The current status of the Kubernetes cluster is as follows:

### Nodes
- **Control Plane Node**: `k8s-ai-control-plane` is in a **Ready** state and running version **v1.33.1**.

### Pods Status
- **Running Pods**:
  - `coredns`: `coredns-674b8bbfcf-rrjdz` and `coredns-674b8bbfcf-w89zr` are both running successfully.
  - `etcd`: Running on `etcd-k8s-ai-control-plane`.
  - Network and Control components like `kindnet`, `kube-apiserver`, `kube-controller-manager`, `kube-proxy`, and `kube-scheduler` are all running.
  - `local-path-provisioner`: Running.

- **Troubled Pods**:
  - In the `default` namespace:
    - `nginx-74f5dd8d8f-zfdmw` has an `ImagePullBackOff` issue.
    - Several `some-app` pods are in a `Pending` state.

### Services
- **ClusterIP Services**:
  - `kubernetes` service is running at IP `10.96.0.1`.
  - KubeDNS service is available at `10.96.0.10` with ports `53/UDP, 53/TCP, 9153/TCP`.

Overall, the cluster's core components and system pods are operational, but there are issues with applications in the 
`default` namespace that need addressing, particularly the `ImagePullBackOff` and `Pending` statuses.
```

OK. That's a pretty good summary. Let's ask it what's the problem with the pending pods:

```
👤 You: find out why the some-app pods are pending
🤖 AI: The `some-app` deployment is configured with a node affinity rule that cannot be satisfied by the current 
cluster node configuration. The specific node affinity configuration is as follows:


affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: no-such-node
          operator: In
          values:
          - "true"

This configuration is attempting to schedule the pods on nodes that have a label `no-such-node` with the value `"true"`. 
However, the current node, `k8s-ai-control-plane`, does not possess such a label. This results in the pods being unable 
to be scheduled.

### Steps to Correct the Issue:

1. **Modify the Deployment's Node Affinity**:
   - If the affinity rules are not necessary, consider removing or adjusting them from the deployment.
   - If specific node selection criteria are required, ensure that the cluster nodes are labeled accordingly.

2. **Label the Node** (if you intend to keep the affinity rule):
   - Add the required label to the node if the intent is to only run `some-app` pods on a specific subset of nodes. 
   Given the current setup, this would involve adding a label like `no-such-node=true` to `k8s-ai-control-plane`, should 
   this be the intended setup.

Would you like to proceed with modifying the deployment configuration or adding a label to the current node?
----------
```

Nice. Let's ask k8s-ai to add the needed label so the pods can be scheduled:

```shell
👤 You: add the label no-such-node to our control plane node
🤖 AI: The label `no-such-node=true` has been successfully added to the control plane node `k8s-ai-control-plane`.
----------
👤 You: what kubectl commands did you use?
🤖 AI: I used the following `kubectl` commands:
1. `kubectl get nodes` - This command was used to list all the nodes in the Kubernetes cluster to identify the control plane node.
2. `kubectl label nodes k8s-ai-control-plane no-such-node=true` - This command was used to add the label `no-such-node=true` to the control plane node named `k8s-ai-control-plane`.
----------
```

As you can see k8s-ai can execute multiple operations to accomplish a task. In this simple case, it first listed the
nodes,
then it added the label to the control plane node. Let's check the status of the pods now:

```shell
kubectl get po
NAME                        READY   STATUS             RESTARTS   AGE
nginx-74f5dd8d8f-zfdmw      0/1     ImagePullBackOff   0          35m
some-app-65696dbff4-2cph8   1/1     Running            0          2m27s
some-app-65696dbff4-8gbp8   1/1     Running            0          2m28s
some-app-65696dbff4-lxgfb   1/1     Running            0          3m13s
```

Excellent. The pods are running now. Let's see if k8s-ai can fix our nginx deployment:

```shell
👤 You: let's go back to the nginx deployment. suggest options how to fix it
🤖 AI: It looks like there is an issue with the `nginx` deployment due to the incorrect image name. The image name 
`nnnnnnnnginx` seems to be invalid or misspelled for the standard `nginx` image. Here are some options to fix the issue:
1. **Update the Image Name:**
   - Correct the image name in the deployment to a valid `nginx` image, such as `nginx:latest`.
2. **Roll Back the Deployment:**
   - If there was a previous version of the deployment with a valid configuration, you can roll back to that version if the deployment history is available.
3. **Check Image Repository:**
   - Verify whether the image exists in your container registry if you're using a custom image. Make sure it's accessible without authentication issues.
4. **Check Compatibility:**
   - Ensure that the specified image version is compatible with your Kubernetes cluster version.
Would you like me to go ahead with the first option and update the image name in the deployment?
----------
```

Those all sound like good options. Let's go with the first one and update the image name to `nginx:latest`:

```
👤 You: option 1 sounds good. go for it.
🤖 AI: The nginx deployment has been updated with the correct image name and successfully rolled out. If you have any more questions or need further assistance, feel free to ask!
----------
```

Alright. Now, that we trust k8s-ai we don't need to run `kubectl get pods` commands ourselves we can just ask k8s-ai to
do it for us.

```
👤 You: show me the pods
🤖 AI: The pods are up and running successfully:
- **nginx-5869d7778c-wjcsz**: Running
- **some-app-65696dbff4-2cph8**: Running
- **some-app-65696dbff4-8gbp8**: Running
- **some-app-65696dbff4-lxgfb**: Running
The nginx deployment is now fixed and operational. If you need further assistance, feel free to ask!
```
