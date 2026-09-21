import { lazy, Suspense, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Toaster } from 'sonner'
import { Activity, BarChart3, Download, LayoutDashboard, Settings2 } from 'lucide-react'
import { Sidebar } from '@/components/layout/Sidebar'
import { ConsoleDrawer } from '@/components/layout/ConsoleDrawer'
import { GlobalStatusBar } from '@/components/layout/GlobalStatusBar'
import type { MonitorOpsTarget } from '@/components/monitor/MonitorOpsCenter'
import { EnvironmentCheck, isEnvChecked } from '@/components/env/EnvironmentCheck'
import { LicenseDisclaimer, isLicenseAccepted } from '@/components/license/LicenseDisclaimer'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { StatePanel } from '@/components/ui/state-panel'

const CrawlerConfigPanel = lazy(() => import('@/components/config/CrawlerConfigPanel').then((module) => ({ default: module.CrawlerConfigPanel })))
const MonitorOverview = lazy(() => import('@/components/monitor/MonitorOverview').then((module) => ({ default: module.MonitorOverview })))
const MonitorDataCenter = lazy(() => import('@/components/monitor/MonitorDataCenter').then((module) => ({ default: module.MonitorDataCenter })))
const MonitorOpsCenter = lazy(() => import('@/components/monitor/MonitorOpsCenter').then((module) => ({ default: module.MonitorOpsCenter })))
const MonitorExport = lazy(() => import('@/components/monitor/MonitorExport').then((module) => ({ default: module.MonitorExport })))

type AppTab = 'overview' | 'data' | 'ops' | 'export' | 'config'
const NAV_TRIGGER_CLASS = 'app-nav-item min-w-0 cursor-pointer flex-col gap-0.5 px-1 py-1.5 text-[11px] sm:flex-row sm:gap-2 sm:px-2 sm:py-2 sm:text-xs lg:gap-3 lg:px-3 lg:py-2.5 lg:text-sm'

function getInitialTab(): AppTab {
  const params = new URLSearchParams(window.location.search)
  const value = params.get('tab')
  const module = params.get('module')
  if (!value && (module === 'topics' || module === 'lifecycle')) return 'data'
  return value === 'data' || value === 'ops' || value === 'export' || value === 'config' ? value : 'overview'
}

function App() {
  const { t } = useTranslation('common')
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


  const openTasks = (status = 'pending', jobId?: number) => {
    setOpsTarget((current) => ({
      section: 'tasks',
      taskStatus: status,
      jobId,
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
    <div className="cyber-grid relative min-h-screen">
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

      <Tabs
        orientation="vertical"
        value={activeTab}
        onValueChange={(value) => navigateTab(value as AppTab)}
        className="app-shell"
      >
        <Sidebar
          onCreateMonitor={() => navigateTab('config')}
          navigation={(
            <TabsList className="app-navigation-list h-auto w-full justify-start border-0 bg-transparent p-0">
              <TabsTrigger value="overview" className={NAV_TRIGGER_CLASS}>
                <LayoutDashboard className="h-4 w-4" aria-hidden="true" />
                {t('tabs.overview')}
              </TabsTrigger>
              <TabsTrigger value="data" className={NAV_TRIGGER_CLASS}>
                <BarChart3 className="h-4 w-4" aria-hidden="true" />
                {t('tabs.monitorData')}
              </TabsTrigger>
              <TabsTrigger value="ops" className={NAV_TRIGGER_CLASS}>
                <Activity className="h-4 w-4" aria-hidden="true" />
                {t('tabs.ops')}
              </TabsTrigger>
              <TabsTrigger value="export" className={NAV_TRIGGER_CLASS}>
                <Download className="h-4 w-4" aria-hidden="true" />
                {t('tabs.export')}
              </TabsTrigger>
              <TabsTrigger value="config" className={NAV_TRIGGER_CLASS}>
                <Settings2 className="h-4 w-4" aria-hidden="true" />
                {t('tabs.config')}
              </TabsTrigger>
            </TabsList>
          )}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <GlobalStatusBar
            onOpenOverview={() => navigateTab('overview')}
            onOpenHealth={openHealth}
            onOpenPending={() => openTasks('pending')}
            onOpenAlerts={() => openAlerts()}
            onOpenSnapshot={() => openTasks('pending')}
          />

          <main id="webui-main-content" tabIndex={-1} className="min-h-0 flex-1 pb-14 focus:outline-none">
            <div className="grid grid-cols-1 gap-4 p-4 md:grid-cols-2 xl:grid-cols-12">
              <TabsContent value="overview" className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <MonitorOverview onOpenTasks={openTasks} onOpenAlerts={openAlerts} onOpenData={openData} onOpenConfig={() => navigateTab('config')} />
                </Suspense>
              </TabsContent>
              <TabsContent value="data" className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <MonitorDataCenter focusAwemeId={dataFocus.awemeId} focusToken={dataFocus.token} />
                </Suspense>
              </TabsContent>
              <TabsContent value="ops" className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <MonitorOpsCenter target={opsTarget} />
                </Suspense>
              </TabsContent>
              <TabsContent value="export" className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <MonitorExport />
                </Suspense>
              </TabsContent>
              <TabsContent value="config" className="mt-0 md:col-span-2 xl:col-span-12">
                <Suspense fallback={<StatePanel variant="loading" title={t('action.loading')} />}>
                  <CrawlerConfigPanel />
                </Suspense>
              </TabsContent>
            </div>
          </main>
        </div>
      </Tabs>

      <ConsoleDrawer />

      {/* Toast notifications - Theme-aware style */}
      <Toaster
        position="top-right"
        toastOptions={{
          className: 'glass-panel font-mono text-cyber-text-primary',
          style: {
            fontFamily: 'JetBrains Mono, monospace',
          },
        }}
      />
    </div>
  )
}

export default App
