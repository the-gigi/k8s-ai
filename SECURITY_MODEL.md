# k8s-ai Security Model

## Two-Tier Authentication System

### 1. API Keys (Long-lived client credentials)
**Purpose:** Authenticate clients to the k8s-ai server
**Storage:** `keys.json` file on server
**Scope:** Access to both A2A Protocol Server (port 9999) and Admin API (port 9998)
**Lifetime:** Persistent until manually revoked

**Management:**
```bash
# Generate a new API key
uv run k8s-ai-server --generate-key --client-name "my-client"

# List all keys
uv run k8s-ai-server --list-keys

# Revoke a key
uv run k8s-ai-server --revoke-key sk-k8sai-xxx
```

### 2. Session Tokens (Short-lived cluster access credentials)
**Purpose:** Temporary access to a specific Kubernetes cluster
**Created by:** Client via Admin API (POST /sessions)
**Contains:** Kubernetes credentials (from client's kubeconfig)
**Scope:** Used as parameters in diagnostic skill calls
**Lifetime:** Time-limited (default 24 hours, configurable via TTL)
**Client-scoped:** Each session is tied to the API key that created it

## Trust Model: Who Provides Cluster Credentials?

**The CLIENT provides kubeconfig**, not the server:

1. **Client has kubeconfig locally** (from `~/.kube/config` or elsewhere)
2. **Client sends kubeconfig to server** via `POST /sessions`
3. **Server stores credentials temporarily** (in memory, with TTL)
4. **Server uses those credentials** when executing diagnostic skills
5. **Session expires automatically** after TTL

This is similar to how `kubectl` works - you trust it with your kubeconfig.

## Authentication Flow

```
┌─────────────────────────┐
│  Client                 │
│  - Has API key          │
│  - Has kubeconfig       │
└─────┬───────────────────┘
      │ 1. API Key + kubeconfig
      ▼
┌─────────────────────────────────────────┐
│  Admin API (port 9998)                  │
│  POST /sessions                         │
│  - Headers: Authorization: Bearer       │
│  - Body: {cluster_name, kubeconfig}     │
│  - Creates session with client_api_key  │
└─────┬───────────────────────────────────┘
      │ 2. Session Token (k8s-ai-session-xxx)
      ▼
┌─────────────────────────────────────────┐
│  A2A Server (port 9999)                 │
│  Skill Call with session_token          │
│  - Headers: Authorization: Bearer       │
│  - Skill params: session_token=...      │
│  - Server uses kubeconfig from session  │
└─────────────────────────────────────────┘
```

## Why Two Layers?

### API Keys (Client Identity)
- **Client authentication** - Who is making the request?
- **Rate limiting** - Track and limit per-client usage
- **Access control** - Grant/revoke access to the entire service
- **Audit trail** - Know which clients accessed the system
- **Session ownership** - Track which client created which sessions

### Session Tokens (Cluster Access)
- **Temporary credentials** - Cluster access with automatic expiration
- **Cluster isolation** - Each session accesses one specific cluster
- **Multiple sessions per cluster** - Different agents can access same cluster with separate sessions
- **Security** - Kubeconfig not sent with every request (only during session creation)
- **Client-scoped** - Sessions are isolated per API key
- **Flexibility** - Create/delete sessions dynamically without restarting server

## Multiple Agents, Same Cluster

**Q: Can multiple agents access the same cluster?**
**A: Yes! Each agent creates their own session.**

```python
# Agent A creates a session
session_a = create_session(api_key_a, "prod-cluster", kubeconfig_a)

# Agent B creates a separate session for the same cluster
session_b = create_session(api_key_b, "prod-cluster", kubeconfig_b)

# Both can work independently
# Sessions don't interfere with each other
```

**Sessions are NOT shared** - each client gets their own session, even for the same cluster.

## Test Automation

The `test_a2a_client.py` demonstrates automated session and server management:

1. **Checks if server is running** - starts it if needed
2. **Reads API key** from `keys.json`
3. **Creates session** via Admin API → gets session token
4. **Uses session token** in diagnostic skill calls
5. **Cleans up session** after test completes
6. **Stops server** if test started it

**Key functions:**
- `ensure_server()` - Start server if not running, returns True if we started it
- `create_session(api_key)` - Creates a session and returns token
- `cleanup_session(api_key, session_token)` - Deletes the session
- `cleanup_server()` - Stops server if we started it
- Uses `try/finally` to ensure cleanup happens even on errors

## Security Best Practices

1. **Never commit keys.json** - Add to .gitignore
2. **Use environment variables** in production:
   ```bash
   export K8S_AI_AUTH_KEYS="key1,key2,key3"
   ```
3. **Short TTLs for tests** - Use 1-hour TTL for automated tests
4. **Long TTLs for interactive use** - Use 24-hour TTL for human users
5. **Regular key rotation** - Generate new API keys periodically
6. **Principle of least privilege** - One key per client/service
7. **Clean up sessions** - Always delete sessions when done

## Example: Automated Test

```python
import requests
import subprocess

# 1. Get API key (from keys.json or environment)
api_key = "sk-k8sai-client-abc123"

# 2. Get kubeconfig from local system
kubeconfig = subprocess.check_output(
    ["kubectl", "config", "view", "--minify", "--raw"],
    text=True
)

# 3. Create session
response = requests.post(
    "http://localhost:9998/sessions",
    headers={"Authorization": f"Bearer {api_key}"},
    json={
        "cluster_name": "my-cluster",
        "kubeconfig": kubeconfig,
        "ttl_hours": 1.0
    }
)
session_token = response.json()["session_token"]

# 4. Use session token in skill calls
skill_call = f"kubernetes_diagnose_issue: session_token={session_token}, issue_description=..."

# 5. List my sessions
response = requests.get(
    "http://localhost:9998/sessions/mine",
    headers={"Authorization": f"Bearer {api_key}"}
)
my_sessions = response.json()["sessions"]

# 6. Clean up
requests.delete(
    f"http://localhost:9998/sessions/{session_token}",
    headers={"Authorization": f"Bearer {api_key}"}
)
```

## Troubleshooting

**"Invalid admin API key"**
- Ensure server has API keys configured (check keys.json exists with valid keys)
- Verify you're using the correct API key from keys.json
- Server must be started with keys in keys.json or via `--auth-key`

**"Invalid or expired session token"**
- Session may have expired (check TTL, default 24h)
- Create a new session to get a fresh token
- Ensure you created the session before using the token
- Check if session was deleted by another process

**"Authentication failed"**
- Check API key is included in Authorization header
- Verify API key format: `Bearer sk-k8sai-...`
- Ensure server is running with authentication enabled

**"Failed to create session"**
- Verify kubeconfig is valid YAML
- Check kubectl can access the cluster: `kubectl cluster-info`
- Ensure context exists in kubeconfig
- Check server logs for detailed error messages

## API Endpoints Reference

### Admin API (port 9998)

**POST /sessions** - Create a new session
```bash
curl -X POST http://localhost:9998/sessions \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "prod",
    "kubeconfig": "<full kubeconfig YAML>",
    "context": "prod-context",
    "ttl_hours": 24.0
  }'
```

**GET /sessions** - List all sessions (admin only)
```bash
curl http://localhost:9998/sessions \
  -H "Authorization: Bearer $API_KEY"
```

**GET /sessions/mine** - List only your sessions
```bash
curl http://localhost:9998/sessions/mine \
  -H "Authorization: Bearer $API_KEY"
```

**DELETE /sessions/{token}** - Delete a session
```bash
curl -X DELETE http://localhost:9998/sessions/k8s-ai-session-xxx \
  -H "Authorization: Bearer $API_KEY"
```

**GET /health** - Health check (no auth required)
```bash
curl http://localhost:9998/health
```
