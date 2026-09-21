import { useId, useRef, useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle, XCircle, Loader2, RefreshCw, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { envApi, EnvCheckResult } from '@/lib/api'
import { useFocusTrap } from '@/hooks/useFocusTrap'

const ENV_CHECK_KEY = 'mediacrawler_env_checked'

interface EnvironmentCheckProps {
  onCheckComplete: (success: boolean) => void
}

// 检查是否已经通过环境检测
export function isEnvChecked(): boolean {
  return localStorage.getItem(ENV_CHECK_KEY) === 'true'
}

// 清除环境检测状态
export function clearEnvCheck(): void {
  localStorage.removeItem(ENV_CHECK_KEY)
}

export function EnvironmentCheck({ onCheckComplete }: EnvironmentCheckProps) {
  const { t } = useTranslation('env')
  const titleId = useId()
  const statusId = useId()
  const detailsId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  useFocusTrap(dialogRef)
  const [status, setStatus] = useState<'checking' | 'success' | 'error'>('checking')
  const [result, setResult] = useState<EnvCheckResult | null>(null)
  const [showDetails, setShowDetails] = useState(false)

  const checkEnvironment = async () => {
    setStatus('checking')
    setResult(null)
    try {
      const response = await envApi.check()
      setResult(response.data)
      if (response.data.success) {
        setStatus('success')
        // 存储到 localStorage
        localStorage.setItem(ENV_CHECK_KEY, 'true')
        // 成功后延迟关闭
        setTimeout(() => onCheckComplete(true), 1500)
      } else {
        setStatus('error')
      }
    } catch (error) {
      setResult({
        success: false,
        message: t('defaultError'),
        error: t('defaultErrorHint')
      })
      setStatus('error')
    }
  }

  useEffect(() => {
    checkEnvironment()
  }, [])

  const handleSkip = () => {
    localStorage.setItem(ENV_CHECK_KEY, 'true')
    onCheckComplete(false)
  }

  const handleRetry = () => {
    checkEnvironment()
  }

  const statusPresentation = {
    checking: {
      icon: Loader2,
      panel: 'border-status-info/20 bg-status-info/10',
      iconClass: 'animate-spin text-status-info',
    },
    success: {
      icon: CheckCircle,
      panel: 'border-status-success/20 bg-status-success/10',
      iconClass: 'text-status-success',
    },
    error: {
      icon: XCircle,
      panel: 'border-status-danger/20 bg-status-danger/10',
      iconClass: 'text-status-danger',
    },
  }[status]
  const StatusIcon = statusPresentation.icon
  const statusMessage = status === 'checking'
    ? t('scanning')
    : status === 'success'
      ? t('success', { message: result?.message })
      : t('error', { message: result?.message })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-950/55 px-4 py-6 backdrop-blur-sm">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={statusId}
        aria-busy={status === 'checking'}
        tabIndex={-1}
        className="relative w-full max-w-lg overflow-hidden rounded-xl border border-cyber-border-subtle bg-cyber-bg-panel shadow-[var(--primitive-shadow-lg)] focus:outline-none"
      >
        <div className="h-1 bg-primary" aria-hidden="true" />
        <div className="p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 flex-none items-center justify-center rounded-lg border border-status-warning/20 bg-status-warning/10 text-status-warning">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 id={titleId} className="text-lg font-semibold text-cyber-text-primary">
                {t('title')}
              </h2>
              <p className="mt-1 text-sm leading-6 text-cyber-text-secondary">{t('requirements')}</p>
            </div>
          </div>

          <div className={`mt-5 rounded-lg border p-4 ${statusPresentation.panel}`}>
            <div id={statusId} role="status" aria-live="polite" className="flex items-start gap-3">
              <StatusIcon className={`mt-0.5 h-5 w-5 flex-none ${statusPresentation.iconClass}`} aria-hidden="true" />
              <span className="text-sm font-medium leading-6 text-cyber-text-primary">{statusMessage}</span>
            </div>

            {status === 'error' && result?.error ? (
              <div className="mt-3 border-t border-cyber-border-subtle/70 pt-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowDetails(!showDetails)}
                  aria-expanded={showDetails}
                  aria-controls={detailsId}
                  className="-ml-2 h-9 px-2 text-sm"
                >
                  {showDetails ? t('hideDetails') : t('showDetails')}
                </Button>
                {showDetails ? (
                  <pre id={detailsId} className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border border-console-header bg-console-surface p-3 text-xs leading-5 text-console-foreground">
                    {result.error}
                  </pre>
                ) : null}
              </div>
            ) : null}
          </div>

          {status === 'error' ? (
            <div className="mt-4 rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary/30 p-4">
              <ol className="space-y-2 text-sm leading-6 text-cyber-text-secondary">
                {[1, 2, 3].map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <span className="numeric-value text-cyber-text-muted">{item}.</span>
                    <span>{t(`requirementsList.${item}`)}</span>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}

          <div className="mt-5 flex flex-col-reverse gap-3 border-t border-cyber-border-subtle pt-5 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={handleSkip} className="sm:w-32">
              {t('skipCheck')}
            </Button>
            {status === 'error' ? (
              <Button onClick={handleRetry} className="sm:w-32">
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                {t('retryCheck')}
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
