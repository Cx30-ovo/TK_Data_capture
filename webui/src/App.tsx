import { lazy, Suspense, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Toaster } from 'sonner'
import { Activity, ArrowUpRight, BarChart3, Download, Radar, Settings2, UsersRound } from 'lucide-react'
import { SpatialHeader, type AppTab } from '@/components/layout/SpatialHeader'
import { SpatialInsights } from '@/components/monitor/SpatialInsights'
import { ConsoleDrawer } from '@/components/layout/ConsoleDrawer'
import { useThemeStore } from '@/store/themeStore'
import { GlobalStatusBar } from '@/components/layout/GlobalStatusBar'
import type { MonitorOpsTarget } from '@/components/monitor/MonitorOpsCenter'
import { EnvironmentCheck, isEnvChecked } from '@/components/env/EnvironmentCheck'
import { LicenseDisclaimer, isLicenseAccepted } from '@/components/license/LicenseDisclaimer'
import { StatePanel } from '@/components/ui/state-panel'

const CrawlerConfigPanel = lazy(() => import('@/components/config/CrawlerConfigPanel').then((module) => ({ default: module.CrawlerConfigPanel })))
const MonitorOverview = lazy(() => import('@/components/monitor/MonitorOverview').then((module) => ({ default: module.MonitorOverview })))
const MonitorDataCenter = lazy(() => import('@/components/monitor/MonitorDataCenter').then((module) => ({ default: module.MonitorDataCenter })))
const MonitorOpsCenter = lazy(() => import('@/components/monitor/MonitorOpsCenter').then((module) => ({ default: module.MonitorOpsCenter })))
const MonitorExport = lazy(() => import('@/components/monitor/MonitorExport').then((module) => ({ default: module.MonitorExport })))
const MonitorHotRank = lazy(() => import('@/components/monitor/MonitorHotRank').then((module) => ({ default: module.MonitorHotRank })))
const AccountMatrix = lazy(() => import('@/components/monitor/AccountMatrix').then((module) => ({ default: module.AccountMatrix })))
const TopicMonitor = lazy(() => import('@/components/monitor/TopicMonitor').then((module) => ({ default: module.TopicMonitor })))


function getInitialTab(): AppTab {
  const params = new URLSearchParams(window.location.search)
  const value = params.get('tab')
  const module = params.get('module')
  if (module === 'hot' && (!value || value === 'data')) return 'hot'
  if (!value && (module === 'overview' || module === 'topics' || module === 'lifecycle' || module === 'strategy' || module === 'hot')) return 'data'
  return value === 'accounts' || value === 'topic-monitor' || value === 'data' || value === 'hot' || value === 'ops' || value === 'export' || value === 'config' ? value : value === 'overview' ? 'overview' : 'insights'
}

function App() {
  const { t } = useTranslation('common')
  const theme = useThemeStore(state => state.resolvedTheme)
  const [insightSearch, setInsightSearch] = useState('')
  const [activeTab, setActiveTab] = useState<AppTab>(getInitialTab)
  const [opsTarget, setOpsTarget] = useState<MonitorOpsTarget>({ section: 'tasks', taskStatus: 'pending', token: 0 })
  const [dataFocus, setDataFocus] = useState<{ awemeId?: string; token: number }>({ token: 0 })
  // Initialize by checking localStorage if license has been accepted
  const [licenseAccepted, setLicenseAccepted] = useState(() => isLicenseAccepted())
  // Initialize by checking localStorage if env check has passed
  const [envChecked, setEnvChecked] = useState(() => isEnvChecked())

  const handleEnvCheckComplete = () => {
    setEnvChecked(true)
  }

  const handleLicenseAccept = () => {
    setLicenseAccepted(true)
  }

  const navigateTab = (tab: AppTab, moduleValue?: 'overview' | 'topics' | 'lifecycle') => {
    setActiveTab(tab)
    const url = new URL(window.location.href)
    url.searchParams.set('tab', tab)
    if (tab !== 'data') url.searchParams.delete('module')
    else if (moduleValue) url.searchParams.set('module', moduleValue)
    window.history.pushState(null, '', url.toString())
  }

  useEffect(() => {
    const handlePopState = () => setActiveTab(getInitialTab())
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])


  const openTasks = (status = 'pending', jobId?: number, accountId?: number) => {
    setOpsTarget((current) => ({
      section: 'tasks',
      taskStatus: status,
      jobId,
      accountId,
      token: current.token + 1,
    }))
    navigateTab('ops')
  }

  const openAlerts = (alertId?: number) => {
    setOpsTarget((current) => ({
      section: 'alerts',
      alertView: alertId ? 'all' : 'unread',
      alertId,
      token: current.token + 1,
    }))
    navigateTab('ops')
  }

  const openData = (awemeId?: string) => {
    setDataFocus((current) => ({ awemeId, token: current.token + 1 }))
    navigateTab('data', 'overview')
  }

  const openHealth = () => {
    setOpsTarget((current) => ({ section: 'health', token: current.token + 1 }))
    navigateTab('ops')
  }

  return (
    <div className="spatial-app">
      <div className="spatial-backdrop" aria-hidden="true" />
      {/* License Disclaimer Modal - Shows first or when triggered */}
      {!licenseAccepted && (
        <LicenseDisclaimer onAccept={handleLicenseAccept} />
      )}

      {/* Environment Check Modal - Shows after license accepted */}
      {licenseAccepted && !envChecked && (
        <EnvironmentCheck onCheckComplete={handleEnvCheckComplete} />
      )}

      <a
        href="#webui-main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[200] focus:rounded-md focus:bg-cyber-bg-panel focus:px-4 focus:py-2 focus:text-sm focus:text-cyber-text-primary focus:ring-2 focus:ring-cyber-neon-cyan"
      >
        {t('skipToContent')}
      </a>

      <SpatialHeader activeTab={activeTab} onNavigate={navigateTab} onSearch={value => { setInsightSearch(value); navigateTab('insights') }} />
      <div className="spatial-app-content">
        <div className="spatial-system-strip">
          <GlobalStatusBar
            onOpenOverview={() => navigateTab('overview')}
            onOpenHealth={openHealth}
            onOpenPending={() => openTasks('pending')}
            onOpenAlerts={() => openAlerts()}
            onOpenSnapshot={() => openTasks('pending')}
          />

        </div>
        <main id="webui-main-content" tabIndex={-1} className={`spatial-main ${activeTab === 'insights' ? 'is-insights' : ''}`}>
          {activeTab === 'insights' && <section className="spatial-home-tab">
            <SpatialInsights search={insightSearch} onSearchChange={setInsightSearch} onOpenData={openData} onOpenTopics={() => navigateTab('topic-monitor')} onOpenHot={() => navigateTab('hot')} onOpenConfig={() => navigateTab('config')} />
          </section>}
          {activeTab !== 'insights' && <div className="spatial-workspace">
            <aside className="spatial-workspace-rail spatial-glass" aria-label="工作区导航"><span>工作区</span>{[
              { id: 'accounts', label: '账号矩阵', icon: UsersRound },
              { id: 'topic-monitor', label: '话题监控', icon: Radar },
              { id: 'data', label: '内容分析', icon: BarChart3 },
              { id: 'hot', label: '平台热榜', icon: Radar },
              { id: 'overview', label: '运行总览', icon: Activity },
              { id: 'ops', label: '任务中心', icon: Activity },
              { id: 'export', label: '数据导出', icon: Download },
              { id: 'config', label: '采集设置', icon: Settings2 },
            ].map(page => <button key={page.id} aria-current={activeTab === page.id ? 'page' : undefined} onClick={() => navigateTab(page.id as AppTab)}><page.icon aria-hidden="true" /><span>{page.label}</span><ArrowUpRight aria-hidden="true" /></button>)}<div className="spatial-console"><ConsoleDrawer /></div></aside>
            <div className="spatial-workspace-content">
              {activeTab === 'accounts' && <section className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <AccountMatrix onOpenSettings={() => navigateTab('config')} />
                </Suspense>
              </section>}
              {activeTab === 'overview' && <section className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <MonitorOverview onOpenTasks={openTasks} onOpenAlerts={openAlerts} onOpenData={openData} onOpenConfig={() => navigateTab('config')} />
                </Suspense>
              </section>}
              {activeTab === 'topic-monitor' && <section className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <TopicMonitor />
                </Suspense>
              </section>}
              {activeTab === 'data' && <section className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <MonitorDataCenter focusAwemeId={dataFocus.awemeId} focusToken={dataFocus.token} />
                </Suspense>
              </section>}
              {activeTab === 'ops' && <section className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <MonitorOpsCenter target={opsTarget} />
                </Suspense>
              </section>}
              {activeTab === 'hot' && <section className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <MonitorHotRank />
                </Suspense>
              </section>}
              {activeTab === 'export' && <section className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <MonitorExport />
                </Suspense>
              </section>}
              {activeTab === 'config' && <section className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <CrawlerConfigPanel onOpenAbnormalTasks={(accountId) => openTasks('failed', undefined, accountId)} />
                </Suspense>
              </section>}
            </div>
          </div>}
        </main>
      </div>

      {/* Toast notifications - Theme-aware style */}
      <Toaster
        position="top-right"
        theme={theme}
        toastOptions={{
          className: 'glass-panel text-cyber-text-primary',
          style: {
            fontFamily: 'inherit',
          },
        }}
      />
    </div>
  )
}

export default App
