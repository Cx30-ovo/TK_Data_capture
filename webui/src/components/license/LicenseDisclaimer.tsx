import { useId, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldAlert, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useFocusTrap } from '@/hooks/useFocusTrap'

const LICENSE_KEY = 'mediacrawler_license_accepted'

// 检查是否已经接受协议
export function isLicenseAccepted(): boolean {
  return localStorage.getItem(LICENSE_KEY) === 'true'
}

// 清除协议接受状态
export function clearLicenseAccepted(): void {
  localStorage.removeItem(LICENSE_KEY)
}

interface LicenseDisclaimerProps {
  onAccept: () => void
}

export function LicenseDisclaimer({ onAccept }: LicenseDisclaimerProps) {
  const { t } = useTranslation('license')
  const titleId = useId()
  const descriptionId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  useFocusTrap(dialogRef)

  const handleConfirm = () => {
    localStorage.setItem(LICENSE_KEY, 'true')
    onAccept()
  }

  const handleDecline = () => {
    // 尝试关闭当前标签页（不会关闭整个浏览器，只关闭当前tab）
    try {
      // 方式1: 直接关闭当前标签页
      window.close()

      // 方式2: 将当前标签页导航到空白页
      setTimeout(() => {
        window.location.href = 'about:blank'
      }, 100)
    } catch {
      // 忽略错误
    }

    // 如果无法关闭（浏览器安全限制），显示拒绝访问页面
    setTimeout(() => {
      document.body.innerHTML = `
        <div style="
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100vh;
          background: #0d1117;
          color: #f85149;
          font-family: 'JetBrains Mono', monospace;
          text-align: center;
          padding: 20px;
        ">
          <div style="font-size: 14px; margin-bottom: 20px; letter-spacing: 0.18em;">ACCESS DENIED</div>
          <div style="font-size: 24px; font-weight: bold; margin-bottom: 10px;">访问已拒绝</div>
          <div style="font-size: 14px; color: #8b949e;">您未同意使用条款，请关闭此标签页</div>
        </div>
      `
    }, 200)
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-slate-950/55 px-4 py-6 backdrop-blur-sm">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        tabIndex={-1}
        className="relative w-full max-w-xl overflow-hidden rounded-xl border border-cyber-border-subtle bg-cyber-bg-panel shadow-[var(--primitive-shadow-lg)] focus:outline-none"
      >
        <div className="h-1 bg-brand-red" aria-hidden="true" />
        <div className="p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 flex-none items-center justify-center rounded-lg border border-status-danger/20 bg-status-danger/10 text-status-danger">
              <ShieldAlert className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 id={titleId} className="text-lg font-semibold text-cyber-text-primary">
                {t('title')}
              </h2>
              <p id={descriptionId} className="mt-1 text-sm leading-6 text-cyber-text-secondary">
                {t('warning')}
              </p>
            </div>
          </div>

          <ol className="mt-5 space-y-2 rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary/30 p-3 sm:p-4">
            {(['line1', 'line2', 'line3', 'line4'] as const).map((line, index) => (
              <li key={line} className="flex items-start gap-3 rounded-md px-1 py-1.5 text-sm leading-6 text-cyber-text-secondary">
                <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-cyber-bg-panel text-xs font-semibold numeric-value text-status-danger">
                  {index + 1}
                </span>
                <span>{t(`content.${line}`)}</span>
              </li>
            ))}
          </ol>

          <a
            href="https://github.com/NanmiCoder/MediaCrawler/blob/main/LICENSE"
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-md px-2 text-sm font-medium text-primary transition-colors hover:bg-cyber-bg-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-cyber-bg-panel"
          >
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
            {t('license')}
          </a>

          <div className="mt-5 flex flex-col-reverse gap-3 border-t border-cyber-border-subtle pt-5 sm:flex-row sm:justify-end">
            <Button onClick={handleDecline} variant="outline" className="sm:w-32">
              {t('decline')}
            </Button>
            <Button onClick={handleConfirm} className="sm:w-64">
              {t('confirm')}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
