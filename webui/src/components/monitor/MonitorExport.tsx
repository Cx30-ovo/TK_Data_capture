import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CalendarDays, CheckCircle2, Download, FileSpreadsheet, FileText, History, ListChecks, Search, Trash2, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { monitorApi, type MonitorReport } from '@/lib/api'
import { StatePanel } from '@/components/ui/state-panel'


type ExportMode = 'posts' | 'snapshots'


function formatDateTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString()
}


function formatDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleDateString()
}


function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}


function reportMetadata(report: MonitorReport) {
  const periodMatch = report.name.match(/douyin_(daily|weekly|monthly)_/)
  const timestampMatch = report.name.match(/(\d{4}-\d{2}-\d{2})_(\d{6})\.md$/)
  const period = periodMatch?.[1] || 'unknown'
  const generated = timestampMatch
    ? new Date(`${timestampMatch[1]}T${timestampMatch[2].slice(0, 2)}:${timestampMatch[2].slice(2, 4)}:${timestampMatch[2].slice(4, 6)}`)
    : new Date(report.modified_at * 1000)
  const end = Number.isNaN(generated.getTime()) ? new Date(report.modified_at * 1000) : generated
  const start = new Date(end)
  if (period === 'daily') start.setHours(0, 0, 0, 0)
  if (period === 'weekly') {
    start.setHours(0, 0, 0, 0)
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7))
  }
  if (period === 'monthly') start.setDate(1)
  return { period, start: start.getTime() / 1000, end: end.getTime() / 1000 }
}


export function MonitorExport() {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const [exportMode, setExportMode] = useState<ExportMode>('posts')
  const [selectedAwemeIds, setSelectedAwemeIds] = useState<string[]>([])
  const [searchText, setSearchText] = useState('')
  const { data: dashboard } = useQuery({
    queryKey: ['monitorDashboard'],
    queryFn: async () => (await monitorApi.getDashboard(100)).data,
    refetchInterval: 30000,
  })
  const { data: reports } = useQuery({
    queryKey: ['monitorReports'],
    queryFn: async () => (await monitorApi.getReports()).data,
    refetchInterval: 30000,
  })
  const generateReport = useMutation({
    mutationFn: (period: 'daily' | 'weekly' | 'monthly') => monitorApi.generateReport(period),
    onSuccess: () => {
      toast.success(t('export.reportGenerated'))
      queryClient.invalidateQueries({ queryKey: ['monitorReports'] })
    },
    onError: (error: Error) => toast.error(`${t('export.reportFailed')}: ${error.message}`),
  })
  const deleteReport = useMutation({
    mutationFn: (name: string) => monitorApi.deleteReport(name),
    onSuccess: (_response, name) => {
      toast.success(t('export.reportDeleted'))
      if (generateReport.data?.data.filename === name) generateReport.reset()
      queryClient.invalidateQueries({ queryKey: ['monitorReports'] })
    },
    onError: (error: Error, name) => {
      const status = (error as Error & { response?: { status?: number } }).response?.status
      if (status === 404) {
        toast.success(t('export.reportDeleted'))
        if (generateReport.data?.data.filename === name) generateReport.reset()
        queryClient.invalidateQueries({ queryKey: ['monitorReports'] })
        return
      }
      toast.error(`${t('export.deleteFailed')}: ${error.message}`)
    },
  })

  const posts = dashboard?.posts || []
  const normalizedSearch = searchText.trim().toLowerCase()
  const filteredPosts = posts.filter((post) => {
    if (!normalizedSearch) return true
    return post.title.toLowerCase().includes(normalizedSearch) || post.aweme_id.includes(normalizedSearch)
  })
  const selectedPosts = posts.filter((post) => selectedAwemeIds.includes(post.aweme_id))
  const reportItems = reports?.reports || []

  const togglePost = (awemeId: string) => {
    setSelectedAwemeIds((current) => current.includes(awemeId)
      ? current.filter((item) => item !== awemeId)
      : [...current, awemeId])
  }

  const reportTypeLabel = (period: string) => t(`export.reportType.${period}`, { defaultValue: period })
  const previewPosts = selectedPosts.length > 0 ? selectedPosts : posts.slice(0, 5)

  return (
    <div className="space-y-3 animate-slide-up">
      <section className="sticky top-12 z-10 rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel/95 p-2 shadow-[0_4px_16px_rgba(15,23,42,0.08)] backdrop-blur">
        <div className="flex flex-wrap items-center gap-2">
          <div className="mr-1 flex items-center gap-2 px-1 text-[10px] font-mono text-cyber-text-muted">
            <Download className="h-3.5 w-3.5 text-cyber-neon-cyan" />
            {t('export.quickActions')}
          </div>
          <a href={monitorApi.exportPostsUrl('csv')} download>
            <Button type="button" variant="outline" size="sm" className="h-8 font-mono text-[10px]"><FileText className="h-3.5 w-3.5" />{t('export.postsCsv')}</Button>
          </a>
          <a href={monitorApi.exportPostsUrl('xlsx')} download>
            <Button type="button" variant="outline" size="sm" className="h-8 font-mono text-[10px]"><FileSpreadsheet className="h-3.5 w-3.5" />{t('export.postsExcel')}</Button>
          </a>
          <a href={selectedAwemeIds.length > 0 ? monitorApi.exportSnapshotsUrl(selectedAwemeIds, 'csv') : undefined} download>
            <Button type="button" variant="outline" size="sm" disabled={selectedAwemeIds.length === 0} className="h-8 font-mono text-[10px]"><History className="h-3.5 w-3.5" />{t('export.snapshotsCsv')}</Button>
          </a>
          <a href={selectedAwemeIds.length > 0 ? monitorApi.exportSnapshotsUrl(selectedAwemeIds, 'xlsx') : undefined} download>
            <Button type="button" variant="outline" size="sm" disabled={selectedAwemeIds.length === 0} className="h-8 font-mono text-[10px]"><FileSpreadsheet className="h-3.5 w-3.5" />{t('export.snapshotsExcel')}</Button>
          </a>
          <div className="hidden h-5 w-px bg-cyber-border-subtle sm:block" />
          {(['daily', 'weekly', 'monthly'] as const).map((period) => (
            <Button key={period} type="button" size="sm" onClick={() => generateReport.mutate(period)} disabled={generateReport.isPending} className="h-8 font-mono text-[10px]">
              <CalendarDays className="h-3.5 w-3.5" />
              {t(`export.generate.${period}`)}
            </Button>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-12">
        <section className="rounded-lg glass-panel float-panel overflow-hidden xl:col-span-4">
          <header className="border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30 px-4 py-3">
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('export.selectObject')}</div>
            <div className="mt-0.5 text-[10px] font-mono text-cyber-text-muted">{t('export.selectObjectHint')}</div>
          </header>
          <div className="space-y-3 p-3">
            <div className="grid grid-cols-2 gap-1 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-1">
              {(['posts', 'snapshots'] as const).map((mode) => (
                <button key={mode} type="button" onClick={() => setExportMode(mode)} className={`rounded px-3 py-2 text-[10px] font-mono transition-colors ${exportMode === mode ? 'bg-cyber-neon-cyan/15 text-cyber-neon-cyan' : 'text-cyber-text-muted hover:bg-cyber-bg-tertiary hover:text-cyber-text-primary'}`}>
                  {t(`export.objectType.${mode}`)}
                </button>
              ))}
            </div>

            {exportMode === 'posts' ? (
              <div className="border-l-2 border-cyber-neon-cyan/60 px-3 py-2">
                <div className="text-2xl font-mono text-cyber-text-primary">{posts.length}</div>
                <div className="mt-1 text-[10px] font-mono text-cyber-text-muted">{t('export.postObjectHint')}</div>
              </div>
            ) : (
              <>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-cyber-text-muted" />
                  <Input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder={t('export.searchPlaceholder')} className="h-8 pl-9 text-xs" />
                </div>
                <div className="max-h-[340px] overflow-y-auto rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20">
                  {filteredPosts.map((post) => (
                    <label key={post.aweme_id} className="flex cursor-pointer items-start gap-3 border-b border-cyber-border-subtle/40 px-3 py-2 last:border-b-0 hover:bg-cyber-bg-tertiary/40">
                      <Checkbox checked={selectedAwemeIds.includes(post.aweme_id)} onCheckedChange={() => togglePost(post.aweme_id)} className="mt-0.5" />
                      <div className="min-w-0 flex-1">
                        <div title={post.title || post.aweme_id} className="truncate text-xs text-cyber-text-primary">{post.title || post.aweme_id}</div>
                        <div className="mt-0.5 text-[9px] font-mono text-cyber-text-muted">{post.aweme_id} · {formatDateTime(post.create_time)}</div>
                      </div>
                    </label>
                  ))}
                  {filteredPosts.length === 0 ? <div className="px-3 py-4 text-xs font-mono text-cyber-text-muted">{t('export.noMatch')}</div> : null}
                </div>
                <div className="flex flex-wrap items-center gap-2 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-2">
                  <span className={`rounded-md border px-2 py-1 text-[10px] font-medium ${selectedAwemeIds.length > 0 ? 'border-cyber-neon-cyan/30 bg-cyber-neon-cyan/10 text-cyber-neon-cyan' : 'border-cyber-border-subtle text-cyber-text-muted'}`}>
                    {t('export.selectedCount', { count: selectedAwemeIds.length })}
                  </span>
                  <Button type="button" variant={filteredPosts.length > 0 ? 'default' : 'outline'} size="sm" disabled={filteredPosts.length === 0} onClick={() => setSelectedAwemeIds(Array.from(new Set([...selectedAwemeIds, ...filteredPosts.map((post) => post.aweme_id)])))} className="h-8 text-[10px]">
                    <ListChecks className="h-3.5 w-3.5" />
                    {t('export.selectAll')}
                  </Button>
                  <Button type="button" variant="outline" size="sm" disabled={selectedAwemeIds.length === 0} onClick={() => setSelectedAwemeIds([])} className="h-8 text-[10px] text-cyber-neon-pink hover:border-cyber-neon-pink/40 hover:text-cyber-neon-pink">
                    <XCircle className="h-3.5 w-3.5" />
                    {t('export.clearSelection')}
                  </Button>
                </div>
              </>
            )}
          </div>
        </section>

        <section className="rounded-lg glass-panel float-panel overflow-hidden xl:col-span-8">
          <header className="border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30 px-4 py-3">
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('export.preview')}</div>
            <div className="mt-0.5 text-[10px] font-mono text-cyber-text-muted">{t('export.previewHint')}</div>
          </header>
          <div className="space-y-3 p-3">
            {generateReport.data ? (
              <div className="rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20">
                <div className="flex flex-wrap items-center gap-2 border-b border-cyber-border-subtle px-3 py-2">
                  <FileText className="h-4 w-4 text-cyber-neon-green" />
                  <span className="min-w-0 flex-1 truncate text-xs font-mono text-cyber-text-primary">{generateReport.data.data.filename}</span>
                  <span className="rounded border border-cyber-neon-green/30 bg-cyber-neon-green/5 px-1.5 py-0.5 text-[9px] font-mono text-cyber-neon-green">{t('export.status.ready')}</span>
                  <a href={generateReport.data.data.download_url} download><Button type="button" size="sm" className="h-7 px-2 font-mono text-[10px]"><Download className="h-3 w-3" />{t('export.download')}</Button></a>
                </div>
                <pre className="max-h-[300px] overflow-auto whitespace-pre-wrap p-3 text-[11px] text-cyber-text-secondary">{generateReport.data.data.content}</pre>
              </div>
            ) : (
              <div className="overflow-hidden rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20">
                <div className="border-b border-cyber-border-subtle px-3 py-2 text-[10px] font-mono text-cyber-text-muted">
                  {exportMode === 'posts' ? t('export.previewPosts') : t('export.previewSnapshots', { count: selectedAwemeIds.length })}
                </div>
                {exportMode === 'posts' ? (
                  <div className="grid grid-cols-2 gap-px bg-cyber-border-subtle/50 md:grid-cols-4">
                    {[t('export.columns.postId'), t('export.columns.publishTime'), t('export.columns.title'), t('export.columns.snapshotCount')].map((column) => <div key={column} className="bg-cyber-bg-panel px-3 py-2 text-[10px] font-mono text-cyber-text-muted">{column}</div>)}
                  </div>
                ) : (
                  <div className="max-h-[300px] overflow-y-auto p-2">
                    {previewPosts.map((post) => (
                      <div key={post.aweme_id} className="flex items-center gap-3 border-b border-cyber-border-subtle/40 px-2 py-2 last:border-b-0">
                        <div className="min-w-0 flex-1"><div className="truncate text-[11px] font-mono text-cyber-text-primary">{post.title || post.aweme_id}</div><div className="mt-0.5 text-[9px] font-mono text-cyber-text-muted">{post.aweme_id}</div></div>
                        <span className="text-[10px] font-mono text-cyber-neon-cyan">{t('export.snapshotCount', { count: post.snapshots.length })}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="flex items-center gap-3 border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30 px-4 py-3">
          <History className="h-4 w-4 text-cyber-neon-cyan" />
          <div><div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('export.recentReports')}</div><div className="mt-0.5 text-[10px] font-mono text-cyber-text-muted">{t('export.reportListHint')}</div></div>
          <span className="ml-auto text-[10px] font-mono text-cyber-text-muted">{reportItems.length}</span>
        </header>
        <div className="max-h-[380px] overflow-y-auto">
          {reportItems.length > 0 ? reportItems.map((report) => {
            const metadata = reportMetadata(report)
            return (
              <div key={report.name} className="flex flex-wrap items-center gap-3 border-b border-cyber-border-subtle/40 px-3 py-2.5 last:border-b-0 hover:bg-cyber-bg-tertiary/20">
                <FileText className="h-4 w-4 flex-shrink-0 text-cyber-neon-cyan" />
                <div className="min-w-[220px] flex-1">
                  <div className="truncate text-xs font-mono text-cyber-text-primary">{report.name}</div>
                  <div className="mt-0.5 text-[9px] font-mono text-cyber-text-muted">{t('export.generatedAt')}: {formatDateTime(report.modified_at)}</div>
                </div>
                <span className="rounded border border-cyber-neon-cyan/30 bg-cyber-neon-cyan/5 px-1.5 py-0.5 text-[9px] font-mono text-cyber-neon-cyan">{reportTypeLabel(metadata.period)}</span>
                <span className="min-w-[150px] text-[10px] font-mono text-cyber-text-muted">{t('export.timeRange')}: {formatDate(metadata.start)} - {formatDate(metadata.end)}</span>
                <span className="min-w-[58px] text-right text-[10px] font-mono text-cyber-text-secondary">{formatSize(report.size)}</span>
                <span className="inline-flex items-center gap-1 text-[9px] font-mono text-cyber-neon-green"><CheckCircle2 className="h-3 w-3" />{t('export.status.ready')}</span>
                <div className="ml-auto flex items-center gap-1">
                  <a href={monitorApi.reportDownloadUrl(report.name)} download><Button type="button" variant="ghost" size="sm" className="h-7 px-2 font-mono text-[10px]"><Download className="h-3 w-3" />{t('export.download')}</Button></a>
                  <Button type="button" variant="ghost" size="sm" title={t('export.delete')} aria-label={t('export.delete')} disabled={deleteReport.isPending} onClick={() => { if (window.confirm(t('export.confirmDelete', { name: report.name }))) deleteReport.mutate(report.name) }} className="h-7 w-7 p-0 text-cyber-text-muted hover:bg-cyber-neon-pink/10 hover:text-cyber-neon-pink"><Trash2 className="h-3.5 w-3.5" /></Button>
                </div>
              </div>
            )
          }) : <StatePanel variant="empty" title={t('export.noReports')} />}
        </div>
      </section>
    </div>
  )
}
