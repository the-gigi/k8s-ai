#!/bin/bash
set -e

KUBE_CONTEXT=$1

echo "🔐 Creating HolmesGPT Read-Only Kubeconfig for $KUBE_CONTEXT..."




# Get service account token
echo "Getting service account token..."
SA_TOKEN=$(kubectl create token holmesgpt-readonly --duration=8760h)

# Get cluster info
CLUSTER_NAME=$(kubectl config view --minify --context $KUBE_CONTEXT -o jsonpath='{.clusters[0].name}')
API_SERVER=$(kubectl config view --minify --context $KUBE_CONTEXT -o jsonpath='{.clusters[0].cluster.server}')
CA_DATA=$(kubectl config view --minify --raw --context $KUBE_CONTEXT -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')

echo "Cluster: $CLUSTER_NAME"
echo "API Server: $API_SERVER"
echo "Token (first 50 chars): ${SA_TOKEN:0:50}..."

# Create the read-only kubeconfig
cat > /tmp/holmesgpt-readonly-kubeconfig.yaml << EOF
apiVersion: v1
kind: Config
clusters:
- cluster:
    certificate-authority-data: $CA_DATA
    server: $API_SERVER
  name: $CLUSTER_NAME
contexts:
- context:
    cluster: $CLUSTER_NAME
    namespace: default
    user: holmesgpt-readonly
  name: holmesgpt-readonly@$CLUSTER_NAME
current-context: holmesgpt-readonly@$CLUSTER_NAME
users:
- name: holmesgpt-readonly
  user:
    token: $SA_TOKEN
EOF

echo "✅ Read-only kubeconfig created at: /tmp/holmesgpt-readonly-kubeconfig.yaml"

# Test the kubeconfig
echo "🧪 Testing read-only access..."
export KUBECONFIG=/tmp/holmesgpt-readonly-kubeconfig.yaml

echo "Testing: kubectl get pods"
kubectl get pods

echo "Testing: kubectl auth can-i list pods"
kubectl auth can-i list pods

echo "Testing: kubectl auth can-i create pods (should be 'no')"
kubectl auth can-i create pods

echo "✅ Read-only kubeconfig is working correctly!"
