import axios from 'axios'
import { getActiveMonitorAccountId } from '@/store/monitorAccountStore'


function accountParams() {
  const accountId = getActiveMonitorAccountId()
  if (accountId === 'all') return { all_accounts: true }
  return accountId ? { account_id: accountId } : undefined
}


function accountQueryString(): string {
  const accountId = getActiveMonitorAccountId()
  if (accountId === 'all') return '&all_accounts=true'
  return accountId ? `&account_id=${accountId}` : ''
}

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Types
export interface CrawlerConfig {
  platform: string
  login_type: string
  crawler_type: string
  keywords: string
  specified_ids: string
  creator_ids: string
  start_page: number
  start_time: string
  end_time: string
  enable_comments: boolean
  enable_sub_comments: boolean
  save_option: string
  cookies: string
  headless: boolean
  max_notes_count?: number | null
  max_comments_count?: number | null
}

export interface CrawlerStatus {
  status: 'idle' | 'running' | 'stopping' | 'error'
  platform: string | null
  crawler_type: string | null
  started_at: string | null
  error_message: string | null
}

export interface LogEntry {
  id: number
  timestamp: string
  level: 'info' | 'warning' | 'error' | 'success' | 'debug'
  message: string
}

export interface DataFile {
  name: string
  path: string
  size: number
  modified_at: number
  record_count: number | null
  type: string
}

export interface FilePreviewResponse {
  data: Record<string, unknown>[]
  total: number
  columns?: string[]
}

export interface Platform {
  value: string
  label: string
  icon: string
}

export interface ConfigOption {
  value: string
  label: string
}

export interface SchedulerConfigPayload {
  enabled: boolean
  times: string[]
  crawler: CrawlerConfig
}

export interface SchedulerStatus {
  enabled: boolean
  times: string[]
  next_run_at: string | null
  last_run_at: string | null
  last_result: string | null
  running: boolean
}

export interface MonitorAccount {
  id: number
  platform: string
  sec_user_id: string
  display_name: string
  profile_url: string | null
  enabled: boolean
  discover_interval_minutes: number
  last_discovered_at: number | null
  created_at: number
  updated_at: number
}

export interface MonitorAccountComparison {
  id: number
  display_name: string
  sec_user_id: string
  enabled: boolean
  profile_url: string | null
  last_discovered_at: number | null
  posts: number
  snapshots: number
  total_interaction: number
  average_interaction: number
  median_interaction: number
  burst_rate: number
  zero_rate: number
  jobs: Record<string, number>
}

export interface MonitorStatus {
  enabled: boolean
  account: MonitorAccount | null
  jobs: Record<string, number>
  loop_running: boolean
}

export interface MonitorConfigPayload {
  sec_user_id: string
  display_name?: string
  profile_url: string
  enabled: boolean
  discover_interval_minutes: number
}

export interface MonitorRunResult {
  status: string
  reason?: string
  created_posts?: number
  created_jobs?: number
  completed?: number
  retried?: number
  failed?: number
}

export interface MonitorSnapshot {
  stage: string
  due_at: number
  captured_at: number
  actual_age_seconds: number
  liked_count: number
  collected_count: number
  comment_count: number
  share_count: number
}

export interface MonitorDashboardPost {
  aweme_id: string
  title: string
  desc: string
  create_time: number
  first_seen_at: number
  canonical_url: string
  cover_url: string | null
  status: string
  snapshots: MonitorSnapshot[]
}

export interface MonitorDashboard {
  generated_at: string
  account: MonitorAccount | null
  counts: {
    posts: number
    snapshots: number
    jobs: Record<string, number>
  }
  posts: MonitorDashboardPost[]
}

export interface MonitorAbnormalJob {
  id: number
  aweme_id: string
  title: string
  stage: string
  due_at: number
  status: string
  miss_reason: string | null
  last_error: string | null
}

export interface MonitorOverview {
  generated_at: string
  now: number
  loop_running: boolean
  account: MonitorAccount | null
  next_discovery_at: number | null
  next_snapshot: {
    id: number
    aweme_id: string
    title: string
    stage: string
    due_at: number
  } | null
  today_new_posts: number
  jobs: Record<string, number>
  abnormal_total: number
  recent_abnormal_jobs: MonitorAbnormalJob[]
}

export interface MonitorJob {
  id: number
  aweme_id: string
  title: string
  canonical_url: string | null
  create_time: number | null
  stage: string
  due_at: number
  status: string
  attempts: number
  last_error: string | null
  miss_reason: string | null
  created_at: number
  started_at: number | null
  finished_at: number | null
  error_category: string
}

export interface MonitorAlert {
  id: number
  alert_type: string
  severity: 'info' | 'warning' | 'error'
  title: string
  message: string
  status: 'unread' | 'read' | 'resolved' | 'ignored'
  created_at: number
  read_at: number | null
}

export interface MonitorHealthCheck {
  key: string
  status: 'ok' | 'warning' | 'error'
  value: string
  detail: string
}

export interface MonitorHealth {
  generated_at: string
  overall_status: 'ok' | 'warning' | 'error'
  checks: MonitorHealthCheck[]
  metrics: {
    jobs?: Record<string, number>
    unread_alerts?: number
    db_size_bytes?: number
    disk_free_bytes?: number
    last_snapshot_at?: number | null
    next_snapshot_at?: number | null
    last_backup_at?: number | null
    backup_count?: number
  }
  system_config?: {
    auto_backup?: boolean
    backup_interval_hours?: number
    backup_retention_days?: number
    log_retention_days?: number
    start_browser_on_service_start?: boolean
    cdp_debug_port?: number
    maintenance_check_interval_seconds?: number
  }
}

export interface MonitorReport {
  name: string
  size: number
  modified_at: number
}

export interface GeneratedMonitorReport {
  filename: string
  content: string
  path: string
  download_url: string
}

export interface AnalyticsStageDelta {
  stage: string
  sample_count: number
  liked_count: number
  collected_count: number
  comment_count: number
  share_count: number
}

export interface AnalyticsGrowthRate {
  aweme_id: string
  title: string
  metric: 'liked_count' | 'collected_count' | 'comment_count' | 'share_count'
  from_stage: string
  to_stage: string
  delta: number
  hours: number
  per_hour: number
  baseline_per_hour?: number
  score?: number
}

export interface AnalyticsEngagementRate {
  aweme_id: string
  title: string
  stage: string
  interaction_total: number
  like_rate: number
  collect_rate: number
  comment_rate: number
  share_rate: number
}

export interface AnalyticsLeaderboardItem {
  aweme_id: string
  title: string
  stage: string
  liked_count: number
  collected_count: number
  comment_count: number
  share_count: number
  score: number
}

export interface AnalyticsHeatmapCell {
  weekday: number
  hour: number
  post_count: number
  avg_likes: number
}

export interface MonitorAnalytics {
  generated_at: string
  stage_deltas: AnalyticsStageDelta[]
  growth_rates: AnalyticsGrowthRate[]
  engagement_rates: AnalyticsEngagementRate[]
  leaderboard: Record<string, AnalyticsLeaderboardItem[]>
  heatmap: AnalyticsHeatmapCell[]
  anomalies: AnalyticsGrowthRate[]
}

export type AIAnalysisType = 'topic' | 'lifecycle' | 'topic_ideas' | 'title_strategy'
export type AIAnalysisStatus = 'done' | 'insufficient_data' | 'failed' | 'running' | 'pending'

export interface AIAnalysisRequest {
  account_id: number
  time_range: '24h' | '7d' | '30d' | 'all'
  post_limit?: number
  force?: boolean
}

export interface AIAnalysisProviderStatus {
  enabled: boolean
  configured: boolean
  provider: string
  base_url: string
  model: string
  api_key_configured: boolean
  timeout_seconds: number
  max_tokens: number
  temperature: number
  vision?: Omit<AIAnalysisProviderStatus, 'vision' | 'vision_sample_limit'>
  vision_sample_limit?: number
}

export interface AITopicCluster {
  name: string
  description: string
  keywords: string[]
  representative_insight: string
  recommended_actions: string[]
  confidence: number
  posts: number
  total_interaction: number
  average_interaction: number
  median_interaction: number
  burst_rate: number
  representative_posts: Array<{
    aweme_id: string
    title: string
    interaction_total: number
    create_time?: number
  }>
}

export interface AITopicAnalysisResult {
  summary: string
  clusters: AITopicCluster[]
  tag_groups: Array<{ name: string; tags: string[]; summary: string }>
  recommendations: string[]
  data_limits: string[]
  source_post_count: number
}

export interface AILifecyclePostInsight {
  aweme_id: string
  title: string
  lifecycle_type: string
  metrics: Record<string, number | null>
  pattern: string
  evidence: string[]
  possible_factors: string[]
  confidence: number
  source: 'model' | 'deterministic'
}

export interface AILifecycleAnalysisResult {
  overall_summary: string
  stage_observation: string
  post_insights: AILifecyclePostInsight[]
  content_patterns: string[]
  anomaly_notes: string[]
  recommendations: string[]
  caveats: string[]
  type_distribution: Record<string, number>
  stage_summary: Array<{ stage: string; sample_count: number; average_interaction: number | null }>
  source_post_count: number
}

export interface AITitleStrategyKeyword {
  keyword: string
  count: number
  ratio: number
  avg_interaction: number
  hit_rate: number
  lift: number
  conclusion: string
}

export interface AITitleLengthGroup {
  len_group: string
  count: number
  ratio: number
  avg_interaction: number
  median_interaction: number
  avg_likes: number
  avg_comments: number
  avg_collects: number
  avg_shares: number
  hit_count: number
  hit_rate: number
}

export interface AITitleStrategyHitWork {
  aweme_id: string
  title: string
  title_clean: string
  publish_time: string
  title_len: number
  interaction: number
  likes: number
  comments: number
  collects: number
  shares: number
  hook_type: string
  why_viral: string
  title_formula: string
  interaction_structure: string
}

export interface AICoverDimensionStat {
  dimension: string
  dimension_name: string
  label: string
  label_name: string
  count: number
  ratio: number
  avg_interaction: number
  hit_rate: number
  lift: number
}

export interface AICoverSample {
  aweme_id: string
  title: string
  cover_url: string
  interaction: number
  is_hit: boolean
  display_tags: string[]
  labels: {
    ocr_text: string
    text_density: string
    text_hook: string
    subject_type: string
    composition: string
    visual_style: string[]
    confidence: number
    [key: string]: string | number | boolean | string[]
  }
}

export interface AICoverAnalysis {
  status: 'done' | 'partial' | 'not_configured' | 'no_covers'
  requested_sample_count: number
  sample_count: number
  missing_cover_count: number
  failed_count?: number
  model: string
  summary: string
  hit_differences: string[]
  recommendations: string[]
  statistics: {
    sample_count: number
    hit_sample_count?: number
    normal_sample_count?: number
    overall_hit_rate: number
    dimensions: AICoverDimensionStat[]
  }
  samples: AICoverSample[]
}

export interface AITitleStrategyResult {
  overview: {
    total_works: number
    hit_count: number
    overall_hit_rate: number
    hit_threshold: number
    interaction_mean: number
    interaction_p90: number
    interaction_stddev: number
    core_finding: string
    title_length_advice: string
    keyword_advice: string
    content_advice: string
  }
  top_keywords: AITitleStrategyKeyword[]
  title_length_analysis: {
    groups: AITitleLengthGroup[]
    long_vs_short: {
      short: { group: string; count: number; avg_interaction: number; median_interaction: number; hit_rate: number; avg_shares: number }
      long: { group: string; count: number; avg_interaction: number; median_interaction: number; hit_rate: number; avg_shares: number }
      long_vs_short_lift_percent: number | null
    }
    best_range: string
    trend: string
    winner: string
    comparison_explanation: string
    recommendation: string
  }
  hit_works: AITitleStrategyHitWork[]
  hit_vs_normal: { key_differences: string[]; common_patterns: string }
  reusable_formulas: Array<{ formula: string; example: string; why_effective: string }>
  next_titles: Array<{ title: string; formula: string; expected_length: number; target_audience: string; hook_type: string }>
  risk_notes: string[]
  title_templates: Array<{ template: string; count: number; ratio: number }>
  cover_analysis?: AICoverAnalysis
  meta: {
    account: string
    period: string
    total_works: number
    hit_threshold: number
    data_limit: string
    interaction_formula: string
    source_post_ids: string[]
    reused_hit_analyses: number
  }
}

export interface AITopicIdea {
  id: number
  title: string
  angle: string
  format: string
  audience: string
  why_now: string
  evidence: string[]
  viral_reason: string
  title_formula: string
  title_variants: string[]
  writing_notes: string
  expected_performance: 'high' | 'medium' | 'low'
  difficulty: 'high' | 'medium' | 'low'
  risk_notes: string
  priority: number
}

export interface AITopicIdeasResult {
  summary: string
  strategy_points: {
    data_basis: string[]
    exclusions: string[]
    principles: string[]
  }
  ideas: AITopicIdea[]
  avoid: string[]
}

export interface AIAnalysisResponse<T = Record<string, unknown>> {
  id: number | null
  analysis_type: AIAnalysisType
  status: AIAnalysisStatus
  cache_hit: boolean
  scope: Record<string, unknown>
  provider?: string
  model?: string
  prompt_version?: string
  result: T
  usage?: Record<string, number>
  created_at?: number
  updated_at?: number
  expires_at?: number | null
  refresh_error?: string
}

// API functions
export const crawlerApi = {
  start: (config: CrawlerConfig) => api.post('/crawler/start', config),
  stop: () => api.post('/crawler/stop'),
  getStatus: () => api.get<CrawlerStatus>('/crawler/status'),
  getLogs: (limit = 100) => api.get<{ logs: LogEntry[] }>('/crawler/logs', { params: { limit } }),
}

export const dataApi = {
  getFiles: (platform?: string, fileType?: string) =>
    api.get<{ files: DataFile[] }>('/data/files', { params: { platform, file_type: fileType } }),
  getFileContent: (path: string, limit = 100) =>
    api.get<FilePreviewResponse>('/data/files/' + path, { params: { preview: true, limit } }),
  getStats: () => api.get('/data/stats'),
  getDownloadUrl: (path: string) => `/api/data/download/${path}`,
}

export const configApi = {
  getPlatforms: () => api.get<{ platforms: Platform[] }>('/config/platforms'),
  getOptions: () =>
    api.get<{
      login_types: ConfigOption[]
      crawler_types: ConfigOption[]
      save_options: ConfigOption[]
    }>('/config/options'),
}

export interface EnvCheckResult {
  success: boolean
  message: string
  output?: string
  error?: string
}

export const envApi = {
  check: () => api.get<EnvCheckResult>('/env/check'),
}

export const schedulerApi = {
  getStatus: () => api.get<SchedulerStatus>('/scheduler/status'),
  update: (payload: SchedulerConfigPayload) => api.post<SchedulerStatus>('/scheduler/config', payload),
  disable: () => api.post<SchedulerStatus>('/scheduler/disable'),
}

export const monitorApi = {
  getAccounts: (includeDisabled = true) =>
    api.get<{ accounts: MonitorAccount[] }>('/monitor/accounts', { params: { include_disabled: includeDisabled } }),
  createAccount: (payload: MonitorConfigPayload) => api.post<MonitorAccount>('/monitor/accounts', payload),
  updateAccount: (accountId: number, payload: Partial<MonitorConfigPayload>) =>
    api.put<MonitorAccount>('/monitor/accounts/' + accountId, payload),
  deleteAccount: (accountId: number) => api.delete('/monitor/accounts/' + accountId),
  discoverAccount: (accountId: number) => api.post<MonitorRunResult>('/monitor/accounts/' + accountId + '/discover'),
  getAccountComparison: (limit = 100) =>
    api.get<{ generated_at: string; accounts: MonitorAccountComparison[] }>('/monitor/accounts/comparison', { params: { limit } }),
  getStatus: (accountId?: number) => api.get<MonitorStatus>('/monitor/status', { params: accountId ? { account_id: accountId } : accountParams() }),
  updateConfig: (payload: MonitorConfigPayload) => api.post('/monitor/config', payload),
  discover: (secUserId?: string) =>
    api.post<MonitorRunResult>('/monitor/discover', null, { params: { sec_user_id: secUserId } }),
  runDueSnapshots: (limit = 50) =>
    api.post<MonitorRunResult>('/monitor/snapshots/run-due', null, { params: { limit } }),
  getDashboard: (limit?: number) =>
    api.get<MonitorDashboard>('/monitor/dashboard', { params: { ...(limit === undefined ? {} : { limit }), ...accountParams() } }),
  getOverview: () => api.get<MonitorOverview>('/monitor/overview', { params: accountParams() }),
  getJobs: (status?: string, limit?: number) =>
    api.get<{ jobs: MonitorJob[]; count: number }>('/monitor/jobs', { params: { ...(status ? { status } : {}), ...(limit === undefined ? {} : { limit }), ...accountParams() } }),
  retryJob: (jobId: number) => api.post('/monitor/jobs/' + jobId + '/retry'),
  retryFailedJobs: (jobIds?: number[]) =>
    api.post<{ updated: number }>('/monitor/jobs/retry-failed', null, {
      params: jobIds && jobIds.length > 0 ? { job_ids: jobIds.join(',') } : undefined,
    }),
  getAlerts: (status?: string, limit = 200) =>
    api.get<{ alerts: MonitorAlert[]; unread: number }>('/monitor/alerts', { params: { status, limit, ...accountParams() } }),
  markAlertRead: (alertId: number) => api.post('/monitor/alerts/' + alertId + '/read'),
  markAllAlertsRead: () => api.post('/monitor/alerts/read-all', null, { params: accountParams() }),
  updateAlertsStatus: (alertIds: number[], status: MonitorAlert['status']) =>
    api.post<{ updated: number; status: MonitorAlert['status'] }>('/monitor/alerts/status', {
      alert_ids: alertIds,
      status,
    }),
  getHealth: () => api.get<MonitorHealth>('/monitor/health', { params: accountParams() }),
  getReports: () => api.get<{ reports: MonitorReport[] }>('/monitor/reports', { params: accountParams() }),
  generateReport: (period: 'daily' | 'weekly' | 'monthly') =>
    api.post<GeneratedMonitorReport>('/monitor/reports/generate', null, { params: { period, ...accountParams() } }),
  exportPostsUrl: (format: 'csv' | 'xlsx') => `/api/monitor/export/posts?format=${format}${accountQueryString()}`,
  exportPostSnapshotsUrl: (awemeId: string, format: 'csv' | 'xlsx') =>
    `/api/monitor/export/post/${encodeURIComponent(awemeId)}?format=${format}${accountQueryString()}`,
  exportSnapshotsUrl: (awemeIds: string[], format: 'csv' | 'xlsx') =>
    `/api/monitor/export/snapshots?aweme_ids=${encodeURIComponent(awemeIds.join(','))}&format=${format}${accountQueryString()}`,
  reportDownloadUrl: (name: string) => `/api/monitor/reports/download?name=${encodeURIComponent(name)}`,
  deleteReport: (name: string) => api.delete('/monitor/reports', { params: { name } }),
  getAnalytics: (limit = 100) => api.get<MonitorAnalytics>('/monitor/analytics', { params: { limit, ...accountParams() } }),
  getAIStatus: () => api.get<AIAnalysisProviderStatus>('/monitor/ai/status'),
  analyzeTopics: (payload: AIAnalysisRequest) =>
    api.post<AIAnalysisResponse<AITopicAnalysisResult>>('/monitor/ai/analyze/topics', payload, { timeout: 300000 }),
  analyzeLifecycle: (payload: AIAnalysisRequest) =>
    api.post<AIAnalysisResponse<AILifecycleAnalysisResult>>('/monitor/ai/analyze/lifecycle', payload, { timeout: 300000 }),
  analyzeTitleStrategy: (payload: AIAnalysisRequest) =>
    api.post<AIAnalysisResponse<AITitleStrategyResult>>('/monitor/ai/analyze/title-strategy', payload, { timeout: 300000 }),
  analyzeTopicIdeas: (payload: { account_id: number; topic_result_id: number; force?: boolean }) =>
    api.post<AIAnalysisResponse<AITopicIdeasResult>>('/monitor/ai/analyze/topic-ideas', payload, { timeout: 300000 }),
  getAIResults: (accountId?: number, analysisType?: AIAnalysisType, status?: AIAnalysisStatus, limit = 20) =>
    api.get<{ results: AIAnalysisResponse[] }>('/monitor/ai/results', {
      params: { account_id: accountId, analysis_type: analysisType, status, limit },
    }),
  getAIResult: (resultId: number) => api.get<AIAnalysisResponse>(`/monitor/ai/results/${resultId}`),
  deleteAIResult: (resultId: number) => api.delete(`/monitor/ai/results/${resultId}`),
}

export default api
