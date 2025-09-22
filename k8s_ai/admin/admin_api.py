"""Out-of-band admin API for cluster management."""

import logging
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn

from ..utils.cluster_sessions import session_manager

logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()

class ClusterRegistrationRequest(BaseModel):
    cluster_name: str
    kubeconfig: str
    context: str | None = None
    ttl_hours: float = 24.0

class ClusterRegistrationResponse(BaseModel):
    success: bool
    session_token: str | None = None
    cluster_name: str | None = None
    api_server: str | None = None
    namespace: str | None = None
    connectivity_status: str | None = None
    connectivity_message: str | None = None
    expires_at: str | None = None
    error: str | None = None

class SessionListResponse(BaseModel):
    total_sessions: int
    sessions: list[Dict[str, Any]]

def verify_admin_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Verify admin API token."""
    # For now, use the same A2A_API_KEY for admin access
    # In production, you'd want a separate ADMIN_API_KEY
    import os
    admin_key = os.getenv("A2A_API_KEY")
    if not admin_key or credentials.credentials != admin_key:
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    return credentials.credentials

def create_admin_app() -> FastAPI:
    """Create FastAPI app for admin operations."""
    app = FastAPI(
        title="HolmesGPT A2A Admin API",
        description="Out-of-band cluster management for HolmesGPT A2A server",
        version="1.0.0"
    )

    @app.post("/clusters/register", response_model=ClusterRegistrationResponse)
    async def register_cluster(
        request: ClusterRegistrationRequest,
        _: str = Depends(verify_admin_token)
    ):
        """Register a Kubernetes cluster."""
        try:
            # Register the cluster
            session_token = session_manager.register_cluster(
                cluster_name=request.cluster_name,
                kubeconfig_yaml=request.kubeconfig,
                context=request.context,
                ttl_hours=request.ttl_hours
            )

            # Test connectivity
            session = session_manager.get_session(session_token)
            if session:
                try:
                    k8s_client = session.get_k8s_client()
                    # Simple connectivity test
                    version_info = k8s_client.get_api_client().api_version
                    connectivity_status = "connected"
                    connectivity_message = f"Successfully connected to Kubernetes API"
                except Exception as e:
                    connectivity_status = "warning"
                    connectivity_message = f"Registered but connectivity test failed: {str(e)}"
            else:
                connectivity_status = "error"
                connectivity_message = "Session creation failed"

            return ClusterRegistrationResponse(
                success=True,
                session_token=session_token,
                cluster_name=request.cluster_name,
                api_server=session.credentials.api_server if session else "unknown",
                namespace=session.credentials.namespace if session else "default",
                connectivity_status=connectivity_status,
                connectivity_message=connectivity_message,
                expires_at=session.expires_at.isoformat() + "Z" if session else None
            )

        except ValueError as e:
            logger.error(f"Validation error in register_cluster: {e}")
            return ClusterRegistrationResponse(
                success=False,
                error=f"Configuration error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error in register_cluster: {e}")
            return ClusterRegistrationResponse(
                success=False,
                error=f"Registration failed: {str(e)}"
            )

    @app.get("/clusters", response_model=SessionListResponse)
    async def list_clusters(_: str = Depends(verify_admin_token)):
        """List all registered clusters."""
        try:
            sessions = session_manager.list_sessions()
            return SessionListResponse(
                total_sessions=len(sessions),
                sessions=sessions
            )
        except Exception as e:
            logger.error(f"Error listing clusters: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to list clusters: {str(e)}")

    @app.delete("/clusters/{session_token}")
    async def unregister_cluster(
        session_token: str,
        _: str = Depends(verify_admin_token)
    ):
        """Unregister a cluster."""
        try:
            # Get session info before removing
            session = session_manager.get_session(session_token)
            if session:
                cluster_name = session.cluster_name
                unregistered = session_manager.unregister_cluster(session_token)
            else:
                cluster_name = "unknown"
                unregistered = False

            return {
                "success": True,
                "session_token": session_token,
                "cluster_name": cluster_name,
                "unregistered": unregistered,
                "message": "Session removed successfully" if unregistered else "Session not found or already expired"
            }

        except Exception as e:
            logger.error(f"Error in unregister_cluster: {e}")
            raise HTTPException(status_code=500, detail=f"Unregistration failed: {str(e)}")

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "holmesgpt-a2a-admin"}

    return app

def serve_admin_api(host: str = "0.0.0.0", port: int = 9998):
    """Start the admin API server."""
    app = create_admin_app()
    logger.info(f"Starting HolmesGPT A2A Admin API on {host}:{port}")
    logger.info("Admin API endpoints:")
    logger.info(f"  POST   http://{host}:{port}/clusters/register")
    logger.info(f"  GET    http://{host}:{port}/clusters")
    logger.info(f"  DELETE http://{host}:{port}/clusters/{{session_token}}")
    logger.info(f"  GET    http://{host}:{port}/health")

    uvicorn.run(app, host=host, port=port, log_config=None)