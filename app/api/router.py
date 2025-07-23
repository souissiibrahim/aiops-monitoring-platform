from fastapi import APIRouter
from app.v1.endpoints.incident_endpoints import router as incident_router
from app.v1.endpoints.rca_analysis_endpoints import router as rca_analysis_router
from app.v1.endpoints.prediction_endpoints import router as prediction_router
from app.v1.endpoints.model_endpoints import router as model_router
from app.v1.endpoints.incident_type_endpoints import router as incident_type_router
from app.v1.endpoints.incident_status_endpoints import router as incident_status_router
from app.v1.endpoints.environment_endpoints import router as environment_router
from app.v1.endpoints.location_endpoints import router as location_router
from app.v1.endpoints.endpoint_type_endpoints import router as endpoint_type_router
from app.v1.endpoints.anomaly_endpoints import router as anomaly_router
from app.v1.endpoints.audit_log_endpoints import router as audit_log_router
from app.v1.endpoints.dependency_graph_endpoints import router as dependency_graph_router
from app.v1.endpoints.response_action_endpoints import router as response_action_router
from app.v1.endpoints.team_endpoints import router as team_router
from app.v1.endpoints.runbook_step_endpoints import router as runbook_step_router
from app.v1.endpoints.runbook_endpoints import router as runbook_router
from app.v1.endpoints.service_endpoint_endpoints import router as service_endpoint_router
from app.v1.endpoints.service_endpoints import router as service_router
from app.v1.endpoints.severity_level_endpoints import router as severity_level_router
from app.v1.endpoints.shap_explanation_endpoints import router as shap_explanation_router
from app.v1.endpoints.team_endpoint_ownership_endpoints import router as team_endpoint_ownership_router
from app.v1.endpoints.telemetry_source_endpoints import router as telemetry_source_router

#from app.v1.endpoints.rca_report_endpoints import router as rca_report_router
#from app.v1.endpoints.log_entry_endpoints import router as log_entry_router
#from app.mcp.mcp_server import mcp_router  
router = APIRouter()
router.include_router(incident_router, prefix="/incidents", tags=["incidents"])
router.include_router(rca_analysis_router, prefix="/rca-analysis", tags=["rca_analysis"])
router.include_router(prediction_router, prefix="/predictions", tags=["predictions"])
router.include_router(model_router, prefix="/models", tags=["models"])
router.include_router(incident_type_router, prefix="/incident-types", tags=["incident_types"])  
router.include_router(incident_status_router, prefix="/incident-statuses", tags=["incident_statuses"])
router.include_router(environment_router, prefix="/environments", tags=["environments"])
router.include_router(location_router, prefix="/locations", tags=["locations"])
router.include_router(endpoint_type_router, prefix="/endpoint-types", tags=["endpoint_types"])
router.include_router(anomaly_router, prefix="/anomalies", tags=["anomalies"])
router.include_router(audit_log_router, prefix="/audit-logs", tags=["audit_logs"])
router.include_router(dependency_graph_router, prefix="/dependency-graph", tags=["dependency_graph"])
router.include_router(response_action_router, prefix="/response-actions", tags=["response_actions"])
router.include_router(team_router, prefix="/teams", tags=["teams"])
router.include_router(runbook_step_router, prefix="/runbook-steps", tags=["runbook_steps"])
router.include_router(runbook_router, prefix="/runbooks", tags=["runbooks"])
router.include_router(service_endpoint_router, prefix="/service-endpoints", tags=["service_endpoints"])
router.include_router(service_router, prefix="/services", tags=["services"])
router.include_router(severity_level_router, prefix="/severity-levels", tags=["severity_levels"])
router.include_router(shap_explanation_router, prefix="/shap-explanations", tags=["shap_explanations"])
router.include_router(team_endpoint_ownership_router, prefix="/team-endpoint-ownerships", tags=["team_endpoint_ownerships"])
router.include_router(telemetry_source_router, prefix="/telemetry-sources", tags=["telemetry_sources"])

#router.include_router(rca_report_router, prefix="/rca-reports", tags=["rca_reports"])
#router.include_router(log_entry_router, prefix="/log-entries", tags=["log_entries"])
#router.include_router(mcp_router, prefix="/mcp", tags=["mcp"])
