import axios from 'axios'

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
  profile_url: string | null
  discover_interval_minutes: number
  last_discovered_at: number | null
}

export interface MonitorStatus {
  enabled: boolean
  account: MonitorAccount | null
  jobs: Record<string, number>
  loop_running: boolean
}

export interface MonitorConfigPayload {
  sec_user_id: string
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
  stage: string
  due_at: number
  status: string
  attempts: number
  last_error: string | null
  miss_reason: string | null
  created_at: number
  started_at: number | null
  finished_at: number | null
}

export interface MonitorAlert {
  id: number
  alert_type: string
  severity: 'info' | 'warning' | 'error'
  title: string
  message: string
  status: 'unread' | 'read'
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
  getStatus: () => api.get<MonitorStatus>('/monitor/status'),
  updateConfig: (payload: MonitorConfigPayload) => api.post('/monitor/config', payload),
  discover: (secUserId?: string) =>
    api.post<MonitorRunResult>('/monitor/discover', null, { params: { sec_user_id: secUserId } }),
  runDueSnapshots: (limit = 50) =>
    api.post<MonitorRunResult>('/monitor/snapshots/run-due', null, { params: { limit } }),
  getDashboard: (limit = 100) =>
    api.get<MonitorDashboard>('/monitor/dashboard', { params: { limit } }),
  getOverview: () => api.get<MonitorOverview>('/monitor/overview'),
  getJobs: (status?: string, limit = 300) =>
    api.get<{ jobs: MonitorJob[]; count: number }>('/monitor/jobs', { params: { status, limit } }),
  retryJob: (jobId: number) => api.post('/monitor/jobs/' + jobId + '/retry'),
  getAlerts: (status?: string, limit = 200) =>
    api.get<{ alerts: MonitorAlert[]; unread: number }>('/monitor/alerts', { params: { status, limit } }),
  markAlertRead: (alertId: number) => api.post('/monitor/alerts/' + alertId + '/read'),
  markAllAlertsRead: () => api.post('/monitor/alerts/read-all'),
  getHealth: () => api.get<MonitorHealth>('/monitor/health'),
  getReports: () => api.get<{ reports: MonitorReport[] }>('/monitor/reports'),
  generateReport: (period: 'daily' | 'weekly' | 'monthly') =>
    api.post<GeneratedMonitorReport>('/monitor/reports/generate', null, { params: { period } }),
  exportPostsUrl: (format: 'csv' | 'xlsx') => `/api/monitor/export/posts?format=${format}`,
  exportPostSnapshotsUrl: (awemeId: string, format: 'csv' | 'xlsx') =>
    `/api/monitor/export/post/${encodeURIComponent(awemeId)}?format=${format}`,
  exportSnapshotsUrl: (awemeIds: string[], format: 'csv' | 'xlsx') =>
    `/api/monitor/export/snapshots?aweme_ids=${encodeURIComponent(awemeIds.join(','))}&format=${format}`,
  reportDownloadUrl: (name: string) => `/api/monitor/reports/download?name=${encodeURIComponent(name)}`,
  deleteReport: (name: string) => api.delete('/monitor/reports', { params: { name } }),
  getAnalytics: (limit = 100) => api.get<MonitorAnalytics>('/monitor/analytics', { params: { limit } }),
}

export default api
