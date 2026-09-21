import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileJson, FileSpreadsheet, FileText, Download, Eye } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { dataApi } from '@/lib/api'
import { formatFileSize, formatDateTime } from '@/lib/utils'
import { DataPreviewDialog } from './preview/DataPreviewDialog'
import type { DataFile } from '@/types/crawler'

interface FileCardProps {
  file: DataFile
}

const fileIcons: Record<string, typeof FileJson> = {
  json: FileJson,
  csv: FileSpreadsheet,
  xlsx: FileSpreadsheet,
  xls: FileSpreadsheet,
}

const fileStyles: Record<string, { icon: string; badge: string }> = {
  json: {
    icon: 'text-cyber-neon-yellow',
    badge: 'border-cyber-neon-yellow/30 bg-cyber-neon-yellow/10 text-cyber-neon-yellow'
  },
  csv: {
    icon: 'text-cyber-neon-green',
    badge: 'border-cyber-neon-green/30 bg-cyber-neon-green/10 text-cyber-neon-green'
  },
  xlsx: {
    icon: 'text-cyber-neon-cyan',
    badge: 'border-cyber-neon-cyan/30 bg-cyber-neon-cyan/10 text-cyber-neon-cyan'
  },
  xls: {
    icon: 'text-cyber-neon-cyan',
    badge: 'border-cyber-neon-cyan/30 bg-cyber-neon-cyan/10 text-cyber-neon-cyan'
  },
}

export function FileCard({ file }: FileCardProps) {
  const { t } = useTranslation('data')
  const [previewOpen, setPreviewOpen] = useState(false)

  const Icon = fileIcons[file.type] || FileText
  const styles = fileStyles[file.type] || {
    icon: 'text-cyber-text-muted',
    badge: 'border-cyber-border-default bg-cyber-bg-tertiary text-cyber-text-secondary'
  }

  // 检查是否支持预览
  const isPreviewable = ['json', 'csv', 'xlsx', 'xls'].includes(file.type.toLowerCase())

  const handleDownload = () => {
    const url = dataApi.getDownloadUrl(file.path)
    window.open(url, '_blank')
  }

  return (
    <>
      <Card variant="interactive" className="overflow-hidden">
        <CardContent className="relative p-4">
          <div className="flex items-start gap-3">
            <div className={`rounded-md border border-cyber-border-default bg-cyber-bg-tertiary/40 p-2 shadow-sm ${styles.icon}`}>
              <Icon className="w-6 h-6" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-mono font-medium text-sm text-cyber-text-primary truncate" title={file.name}>
                {file.name}
              </h3>
              <p className="text-xs text-cyber-text-muted mt-1 font-mono">
                {formatFileSize(file.size)}
                {file.record_count !== null && (
                  <span className="text-cyber-neon-green"> | {t('file.entries', { count: file.record_count })}</span>
                )}
              </p>
              <p className="text-xs text-cyber-text-muted mt-1 font-mono">
                {formatDateTime(file.modified_at)}
              </p>
            </div>
          </div>

          <div className="flex items-center justify-between mt-3 pt-3 border-t border-cyber-border-subtle">
            <Badge variant="outline" className={`text-[10px] font-mono ${styles.badge}`}>
              .{file.type.toUpperCase()}
            </Badge>
            <div className="flex gap-1 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100">
              {isPreviewable && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 font-mono text-cyber-neon-cyan hover:text-cyber-neon-cyan hover:bg-cyber-neon-cyan/10"
                  onClick={() => setPreviewOpen(true)}
                >
                  <Eye className="w-3 h-3 mr-1" />
                  {t('file.preview')}
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 font-mono text-cyber-neon-cyan hover:text-cyber-neon-cyan hover:bg-cyber-neon-cyan/10"
                onClick={handleDownload}
              >
                <Download className="w-3 h-3 mr-1" />
                {t('file.extract')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 预览对话框 */}
      {isPreviewable && (
        <DataPreviewDialog
          file={file}
          open={previewOpen}
          onOpenChange={setPreviewOpen}
        />
      )}
    </>
  )
}
