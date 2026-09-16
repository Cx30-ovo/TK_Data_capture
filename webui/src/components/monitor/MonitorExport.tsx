import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CalendarDays, Download, FileSpreadsheet, FileText, History, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { monitorApi } from '@/lib/api'


function formatDateTime(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString()
}


function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}


export function MonitorExport() {
  const { t } = useTranslation('config')
  const queryClient = useQueryClient()
  const [selectedAwemeId, setSelectedAwemeId] = useState('')
  const { data: dashboard } = useQuery({
    queryKey: ['monitorDashboard'],
    queryFn: async () => (await monitorApi.getDashboard()).data,
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
      if (generateReport.data?.data.filename === name) {
        generateReport.reset()
      }
      queryClient.invalidateQueries({ queryKey: ['monitorReports'] })
    },
    onError: (error: Error, name) => {
      const status = (error as Error & { response?: { status?: number } }).response?.status
      if (status === 404) {
        toast.success(t('export.reportDeleted'))
        if (generateReport.data?.data.filename === name) {
          generateReport.reset()
        }
        queryClient.invalidateQueries({ queryKey: ['monitorReports'] })
        return
      }
      toast.error(`${t('export.deleteFailed')}: ${error.message}`)
    },
  })

  const posts = dashboard?.posts || []
  const selectedPost = posts.find((post) => post.aweme_id === selectedAwemeId)

  return (
    <div className="space-y-4 animate-slide-up">
      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
          <div className="h-8 w-8 rounded-md bg-cyber-bg-tertiary border border-cyber-border-subtle flex items-center justify-center">
            <Download className="h-4 w-4 text-cyber-neon-cyan" />
          </div>
          <div>
            <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('export.title')}</div>
            <div className="text-[10px] text-cyber-text-muted">{t('export.description')}</div>
          </div>
        </header>

        <div className="p-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="space-y-3">
            <div className="text-xs font-mono text-cyber-text-primary">{t('export.postsList')}</div>
            <div className="flex flex-wrap gap-2">
              <a href={monitorApi.exportPostsUrl('csv')} download>
                <Button type="button" variant="outline" size="sm" className="h-8 font-mono text-[10px]">
                  <FileText className="w-3.5 h-3.5" />
                  CSV
                </Button>
              </a>
              <a href={monitorApi.exportPostsUrl('xlsx')} download>
                <Button type="button" variant="outline" size="sm" className="h-8 font-mono text-[10px]">
                  <FileSpreadsheet className="w-3.5 h-3.5" />
                  Excel
                </Button>
              </a>
            </div>
          </div>

          <div className="space-y-3">
            <div className="text-xs font-mono text-cyber-text-primary">{t('export.postHistory')}</div>
            <Select value={selectedAwemeId} onValueChange={setSelectedAwemeId}>
              <SelectTrigger className="h-9 text-xs">
                <SelectValue placeholder={t('export.selectPost')} />
              </SelectTrigger>
              <SelectContent>
                {posts.map((post) => (
                  <SelectItem key={post.aweme_id} value={post.aweme_id}>
                    {post.title || post.aweme_id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="flex flex-wrap gap-2">
              <a href={selectedPost ? monitorApi.exportPostSnapshotsUrl(selectedPost.aweme_id, 'csv') : undefined} download>
                <Button type="button" variant="outline" size="sm" disabled={!selectedPost} className="h-8 font-mono text-[10px]">
                  <History className="w-3.5 h-3.5" />
                  CSV
                </Button>
              </a>
              <a href={selectedPost ? monitorApi.exportPostSnapshotsUrl(selectedPost.aweme_id, 'xlsx') : undefined} download>
                <Button type="button" variant="outline" size="sm" disabled={!selectedPost} className="h-8 font-mono text-[10px]">
                  <FileSpreadsheet className="w-3.5 h-3.5" />
                  Excel
                </Button>
              </a>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-lg glass-panel float-panel overflow-hidden">
        <header className="px-4 py-3 border-b border-cyber-border-subtle/50 flex items-center gap-3 bg-cyber-bg-tertiary/30">
          <CalendarDays className="h-4 w-4 text-cyber-neon-green" />
          <div className="text-xs font-mono font-semibold text-cyber-text-primary">{t('export.reports')}</div>
        </header>
        <div className="p-4 space-y-4">
          <div className="flex flex-wrap gap-2">
            {(['daily', 'weekly', 'monthly'] as const).map((period) => (
              <Button
                key={period}
                type="button"
                variant="outline"
                onClick={() => generateReport.mutate(period)}
                disabled={generateReport.isPending}
                className="h-9 font-mono text-xs"
              >
                <CalendarDays className="w-3.5 h-3.5" />
                {t(`export.period.${period}`)}
              </Button>
            ))}
          </div>

          {generateReport.data ? (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-mono text-cyber-text-primary">{generateReport.data.data.filename}</span>
                <a href={generateReport.data.data.download_url} download>
                  <Button type="button" size="sm" className="h-8 font-mono text-[10px]">
                    <Download className="w-3.5 h-3.5" />
                    {t('export.download')}
                  </Button>
                </a>
              </div>
              <pre className="max-h-[420px] overflow-auto rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-4 text-[11px] whitespace-pre-wrap text-cyber-text-secondary">
                {generateReport.data.data.content}
              </pre>
            </div>
          ) : null}

          <div className="space-y-2">
            <div className="text-[10px] font-mono text-cyber-text-muted">{t('export.recentReports')}</div>
            {(reports?.reports || []).length > 0 ? reports?.reports.map((report) => (
              <div key={report.name} className="flex items-center gap-3 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 px-3 py-2">
                <FileText className="w-4 h-4 text-cyber-neon-cyan" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-mono text-cyber-text-primary truncate">{report.name}</div>
                  <div className="text-[10px] font-mono text-cyber-text-muted">{formatDateTime(report.modified_at)} · {formatSize(report.size)}</div>
                </div>
                <a href={monitorApi.reportDownloadUrl(report.name)} download>
                  <Button type="button" variant="ghost" size="sm" className="h-7 px-2 font-mono text-[10px]">
                    {t('export.download')}
                  </Button>
                </a>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  title={t('export.delete')}
                  aria-label={t('export.delete')}
                  disabled={deleteReport.isPending}
                  onClick={() => {
                    if (window.confirm(t('export.confirmDelete', { name: report.name }))) {
                      deleteReport.mutate(report.name)
                    }
                  }}
                  className="h-7 w-7 p-0 text-cyber-text-muted hover:text-cyber-neon-pink hover:bg-cyber-neon-pink/10"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            )) : (
              <div className="py-4 text-xs font-mono text-cyber-text-muted">{t('export.noReports')}</div>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
