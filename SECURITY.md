# 🔒 HolmesGPT A2A Security Guide

## Critical Security Requirement

**NEVER provide HolmesGPT with admin kubeconfig credentials. ALWAYS use read-only service accounts.**

## Why Read-Only Access Matters

HolmesGPT performs only diagnostic operations (listing pods, reading events, checking logs), yet admin kubeconfig gives full cluster-admin privileges. This creates unnecessary security risk.

| Permission Level | Risks | Recommended |
|------------------|-------|-------------|
| **Admin kubeconfig** | ❌ Can create/delete/modify any resource<br/>❌ Full cluster access<br/>❌ Can escalate privileges | **NO** |
| **Read-only RBAC** | ✅ Can only read cluster state<br/>✅ Cannot modify resources<br/>✅ Minimal attack surface | **YES** |

## Read-Only RBAC Setup Guide

### Step 1: Create Read-Only Service Account

Apply the RBAC manifests to create a service account with minimal diagnostic permissions:

```bash
# Create read-only service account and RBAC
kubectl apply -f rbac-readonly.yaml
```

The RBAC policy (`rbac-readonly.yaml`) grants only these permissions:
- `get`/`list` access to pods, events, logs, services, deployments
- **No** `create`, `update`, `delete`, or `patch` permissions
- **No** access to secrets or sensitive resources

### Step 2: Generate Read-Only Kubeconfig

Use the provided script to create a kubeconfig with read-only credentials:

```bash
# Generate read-only kubeconfig with service account token
./create_readonly_kubeconfig.sh
```

This creates `/tmp/holmesgpt-readonly-kubeconfig.yaml` with:
- Service account token authentication
- Read-only permissions only
- 1-year token validity

### Step 3: Verify Security Constraints

Test that the read-only kubeconfig properly restricts access:

```bash
export KUBECONFIG=/tmp/holmesgpt-readonly-kubeconfig.yaml

# These should work (read operations)
kubectl get pods                  # ✅ ALLOWED
kubectl get events               # ✅ ALLOWED
kubectl logs <pod-name>          # ✅ ALLOWED

# These should be denied (write operations)
kubectl auth can-i create pods   # ❌ Should return "no"
kubectl auth can-i delete pods   # ❌ Should return "no"
```

### Step 4: Test with HolmesGPT

Use the read-only kubeconfig when registering clusters:

```bash
# Test with read-only credentials
python test_readonly_secure.py
```

This test validates:
- ✅ Diagnostic operations work correctly
- ✅ Write operations are blocked
- ✅ Security constraints are enforced

## What HolmesGPT Actually Uses

Based on code analysis (`kubernetes.py:62-68` and `k8s_client.py:102-148`), HolmesGPT only performs these **read-only** operations:

| API Call | Resource | Verb | Purpose |
|----------|----------|------|---------|
| `list_namespaced_pod()` | `pods` | `list` | Count pods, check status |
| `list_namespaced_event()` | `events` | `list` | Find warning/error events |
| `read_namespaced_pod_log()` | `pods/log` | `get` | Analyze pod logs |
| `read_namespaced_pod()` | `pods` | `get` | Get specific pod details |
| `read_namespaced_deployment()` | `deployments` | `get` | Check deployment status |

## RBAC Policy Details

The `rbac-readonly.yaml` file contains:

```yaml
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: holmesgpt-readonly
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: holmesgpt-readonly
rules:
# Core resources - read only for diagnostics
- apiGroups: [""]
  resources:
    - "pods"
    - "pods/log"
    - "events"
    - "nodes"
    - "services"
    - "endpoints"
    - "configmaps"
    - "persistentvolumes"
    - "persistentvolumeclaims"
    - "namespaces"
  verbs: ["get", "list"]

# Apps resources - read only
- apiGroups: ["apps"]
  resources:
    - "deployments"
    - "replicasets"
    - "daemonsets"
    - "statefulsets"
  verbs: ["get", "list"]

# Networking resources - read only
- apiGroups: ["networking.k8s.io"]
  resources:
    - "networkpolicies"
    - "ingresses"
  verbs: ["get", "list"]

# Metrics (if available)
- apiGroups: ["metrics.k8s.io"]
  resources: ["pods", "nodes"]
  verbs: ["get", "list"]

# Extensions for troubleshooting
- apiGroups: ["extensions"]
  resources: ["ingresses"]
  verbs: ["get", "list"]

# Batch jobs
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: holmesgpt-readonly
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: holmesgpt-readonly
subjects:
- kind: ServiceAccount
  name: holmesgpt-readonly
  namespace: default
```

## Manual Token Creation

For newer Kubernetes versions that don't auto-create service account secrets:

```bash
# Create long-lived token (1 year)
kubectl create token holmesgpt-readonly --duration=8760h

# Or create a permanent secret (not recommended)
kubectl create secret generic holmesgpt-readonly-token \
  --from-literal=token=$(kubectl create token holmesgpt-readonly --duration=8760h) \
  --type=Opaque
```

## Security Validation Results

When using the read-only setup, you should see these results:

```bash
🔐 Testing HolmesGPT A2A with Read-Only Credentials
============================================================

🔐 STEP 1: Register cluster with READ-ONLY kubeconfig
--------------------------------------------------
✅ Read-only cluster registered successfully!
   • Cluster: secure-k8s-readonly
   • Session Token: holmes-session-...
   • Connectivity: warning
   • 🔒 Security: READ-ONLY ACCESS ONLY

🔍 STEP 2: Test diagnostics with read-only credentials
--------------------------------------------------
✅ Agent card retrieved
✅ A2A client created for read-only testing
🔍 Testing: kubernetes_investigate_alert: session_token=...
✅ Read-only diagnostic completed:
✅ Skill 'kubernetes_investigate_alert' executed successfully:

{
  "investigation_type": "general_cluster_health",
  "cluster_data": {
    "pod_count": 3,
    "warning_events": 3,
    "healthy_pods": 0,
    "failed_pods": 0
  },
  "severity": "medium",
  "confidence": 0.9
}

🎯 SECURITY VALIDATION:
   • ✅ Read operations: SUCCESSFUL
   • ✅ Pod listing: ALLOWED
   • ✅ Event reading: ALLOWED
   • ✅ Write operations: BLOCKED (as expected)
   • 🔒 Security posture: SECURE
```

## Production Security Recommendations

1. **Use the read-only kubeconfig**: Never use admin credentials
2. **Rotate tokens regularly**: Regenerate service account tokens quarterly
3. **Namespace isolation**: Create separate service accounts per namespace if needed
4. **Network policies**: Restrict HolmesGPT server network access
5. **Audit logging**: Monitor all API calls made by the service account
6. **Token expiration**: Use shorter-lived tokens in production (e.g., 24h with automatic rotation)
7. **Least privilege**: Remove unused permissions from the RBAC policy
8. **Network segmentation**: Run HolmesGPT server in isolated network segments

## Security Benefits

- ✅ **Minimal Attack Surface**: HolmesGPT can only read cluster state
- ✅ **No Resource Modification**: Cannot create, modify, or delete resources
- ✅ **No Privilege Escalation**: Cannot access secrets or elevate permissions
- ✅ **Audit Trail**: All operations are logged and traceable
- ✅ **Network Isolation**: Can be deployed with network policies for additional security
- ✅ **Token Rotation**: Supports regular credential rotation for defense in depth

## Current vs Secure Flow

**Current (Insecure):**
```
AI System → Admin Kubeconfig → HolmesGPT A2A → Full Admin Access
```

**Recommended (Secure):**
```
AI System → Read-Only Kubeconfig → HolmesGPT A2A → Read-Only Access
```

The HolmesGPT A2A server will work exactly the same, but with dramatically reduced security risk.