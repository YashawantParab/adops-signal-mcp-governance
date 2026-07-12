export type RiskLevel = "Low" | "Medium" | "High" | "Unknown";

export interface CampaignSummary {
  id: number;
  advertiser_id: number;
  advertiser_name?: string;
  campaign_name: string;
  campaign_type: string;
  start_date: string;
  end_date: string;
  goal_impressions: number;
  delivered_impressions: number;
  budget: number;
  status: string;
  target_countries: string[];
  target_devices: string[];
  target_content_categories: string[];
  frequency_cap: number;
  bid_floor: number;
  priority_level: string;
  pacing_percentage: number;
  risk_level: RiskLevel;
  main_issue: string;
  creative_status: string;
}

export interface Creative {
  id: number;
  campaign_id: number;
  creative_name: string;
  format: string;
  duration_seconds: number;
  vast_url: string;
  approval_status: string;
  rejection_reason?: string | null;
  last_validated_at: string;
}

export interface VastError {
  id: number;
  creative_id: number;
  error_code: string;
  error_message: string;
  severity: RiskLevel | string;
  detected_at: string;
}

export interface InventorySummary {
  eligible_segments: number;
  eligible_daily_impressions: number;
  total_daily_impressions: number;
  eligible_inventory_percentage: number;
  constrained_dimensions: string[];
}

export interface BidSummary {
  total_bids: number;
  win_rate: number;
  below_floor_rate: number;
  avg_bid_price: number;
  avg_floor_price: number;
}

export interface CampaignHealth {
  campaign_id: number;
  pacing_percentage: number;
  expected_delivery: number;
  actual_delivery: number;
  risk_level: RiskLevel;
  creative_status: string;
  vast_error_count: number;
  inventory: InventorySummary;
  bid_analysis: BidSummary;
  main_suspected_issue: string;
}

export interface CampaignDetail extends CampaignSummary {
  health: CampaignHealth;
  creatives: Creative[];
  vast_errors: VastError[];
  pacing_history: Array<{
    date: string;
    expected_delivery: number;
    actual_delivery: number;
    pacing_percentage: number;
    risk_level: RiskLevel;
  }>;
}

export interface EvidenceItem {
  id?: string | null;
  source: string;
  message: string;
  metric?: string | null;
  retrieved_at?: string | null;
}

export interface RootCause {
  cause: string;
  impact: RiskLevel | string;
  evidence: string;
  evidence_ids: string[];
}

export interface Recommendation {
  id: number;
  campaign_id: number;
  title: string;
  description: string;
  expected_impact: RiskLevel | string;
  risk_level: RiskLevel | string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  decision_reason?: string | null;
  decided_at?: string | null;
  decided_by_user_id?: number | null;
  decided_by_name?: string | null;
  decided_by_role?: string | null;
}

export interface PlaybookSource {
  source: string;
  title: string;
  snippet: string;
  score: number;
  embedding_provider: string;
  search_backend: string;
}

export interface AgentDiagnosis {
  campaign_id: number;
  diagnosis: string;
  root_causes: RootCause[];
  tools_called: string[];
  evidence: EvidenceItem[];
  recommendations: Recommendation[];
  confidence_score: number;
  risk_level: RiskLevel | string;
  human_approval_required: boolean;
  query_intent: string;
  execution_mode: "llm_rag" | "fallback";
  model_name: string;
  prompt_version: string;
  latency_ms: number;
  retrieved_documents: string[];
  playbook_sources: PlaybookSource[];
}

export interface ToolDescriptor {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_contract: string;
}

export interface AuditLog {
  id: number;
  campaign_id: number;
  user_query: string;
  tools_called: string[];
  evidence: EvidenceItem[];
  diagnosis: string;
  confidence_score: number;
  query_intent: string;
  execution_mode: "llm_rag" | "fallback";
  model_name: string;
  latency_ms: number;
  request_id?: string | null;
  created_at: string;
}

export interface ClientSummaryResponse {
  campaign_id: number;
  summary: string;
  omitted_internal_details: string[];
}

export interface VastValidationResponse {
  valid: boolean;
  creative_id?: number | null;
  approval_status: string;
  errors: VastError[];
  suggested_fix: string;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: "admin" | "adops_manager" | "product_manager" | "viewer" | "demo_viewer";
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface SystemStatus {
  status: string;
  environment: string;
  version: string;
  ai_mode: "llm_rag" | "grounded_fallback";
  model: string;
  rag_provider: string;
  auth_enabled: boolean;
}

export interface RoiAssumptions {
  campaigns_per_month: number;
  incident_rate: number;
  minutes_per_incident_before: number;
  minutes_per_incident_after: number;
  loaded_hourly_cost_eur: number;
  average_campaign_value_eur: number;
  revenue_at_risk_rate: number;
  recovery_rate: number;
}

export interface RoiEstimate {
  incidents_per_month: number;
  hours_saved_per_month: number;
  labor_savings_eur: number;
  revenue_protected_eur: number;
  total_monthly_value_eur: number;
  annualized_value_eur: number;
  assumptions: RoiAssumptions;
}

// --- MCP governance -----------------------------------------------------

export interface MCPToolDescriptor {
  name: string;
  description: string;
  read_only: boolean;
  input_schema: Record<string, unknown>;
  output_contract: string;
  category: string;
  permission_level: string;
  approval_required: boolean;
  risk_level: string;
  call_count: number;
  failure_rate: number;
  last_used_at?: string | null;
}

export interface MCPToolTimelineEntry {
  step: number;
  tool_name: string;
  status: string;
  latency_ms: number;
  summary: string;
}

export interface MCPAgentRunResponse {
  agent_run_id: string;
  status: string;
  campaign_id: string;
  summary: string;
  risk_score: number;
  risk_level: string;
  approval_required: boolean;
  blocked: boolean;
  final_recommendation: string;
  tool_timeline: MCPToolTimelineEntry[];
}

export interface MCPToolCall {
  id: number;
  agent_run_id: number;
  tool_name: string;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  status: string;
  latency_ms: number;
  created_at: string;
}

export interface MCPPolicyCheck {
  id: number;
  agent_run_id: number;
  policy_name: string;
  result: string;
  matched_rules: unknown[];
  citation: string;
  created_at: string;
}

export interface MCPBlockedAction {
  id: number;
  agent_run_id: number;
  tool_name: string;
  reason: string;
  risk_level: string;
  created_at: string;
}

export interface MCPApprovalRequest {
  id: number;
  agent_run_id: number;
  campaign_id: number;
  campaign_name?: string | null;
  proposed_action: string;
  risk_score: number;
  risk_level: string;
  rationale: string;
  status: "pending" | "approved" | "rejected";
  reviewer_id?: number | null;
  reviewer_name?: string | null;
  reviewed_at?: string | null;
  created_at: string;
}

export interface MCPAgentRun {
  id: number;
  user_query: string;
  campaign_id: number;
  campaign_name?: string | null;
  status: string;
  risk_level: string;
  risk_score: number;
  final_recommendation: string;
  approval_required: boolean;
  created_at: string;
  completed_at?: string | null;
}

export interface MCPAgentRunDetail extends MCPAgentRun {
  tool_calls: MCPToolCall[];
  approval_requests: MCPApprovalRequest[];
  policy_checks: MCPPolicyCheck[];
  blocked_actions: MCPBlockedAction[];
}

export interface MCPSummary {
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
  approval_requests: Record<string, number>;
  blocked_actions: number;
  policy_checks: Record<string, number>;
  average_risk_score: number;
  tool_calls: number;
  average_tool_latency_ms: number;
}
