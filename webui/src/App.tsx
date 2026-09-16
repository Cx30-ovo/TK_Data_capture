import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Toaster } from 'sonner'
import { Activity, BarChart3, Download, LayoutDashboard, Settings2 } from 'lucide-react'
import { Sidebar } from '@/components/layout/Sidebar'
import { ConsoleDrawer } from '@/components/layout/ConsoleDrawer'
import { GlobalStatusBar } from '@/components/layout/GlobalStatusBar'
import { CrawlerConfigPanel } from '@/components/config/CrawlerConfigPanel'
import { MonitorOverview } from '@/components/monitor/MonitorOverview'
import { MonitorDataCenter } from '@/components/monitor/MonitorDataCenter'
import { MonitorOpsCenter, type MonitorOpsTarget } from '@/components/monitor/MonitorOpsCenter'
import { MonitorExport } from '@/components/monitor/MonitorExport'
import { EnvironmentCheck, isEnvChecked } from '@/components/env/EnvironmentCheck'
import { LicenseDisclaimer, isLicenseAccepted } from '@/components/license/LicenseDisclaimer'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

function App() {
  const { t } = useTranslation('common')
  const [activeTab, setActiveTab] = useState('overview')
  const [opsTarget, setOpsTarget] = useState<MonitorOpsTarget>({ section: 'tasks', taskStatus: 'pending', token: 0 })
  const [dataFocusAwemeId, setDataFocusAwemeId] = useState<string>()
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


  const openTasks = (status = 'pending', jobId?: number) => {
    setOpsTarget((current) => ({
      section: 'tasks',
      taskStatus: status,
      jobId,
      token: current.token + 1,
    }))
    setActiveTab('ops')
  }

  const openAlerts = (alertId?: number) => {
    setOpsTarget((current) => ({
      section: 'alerts',
      alertView: alertId ? 'all' : 'unread',
      alertId,
      token: current.token + 1,
    }))
    setActiveTab('ops')
  }

  const openData = (awemeId?: string) => {
    setDataFocusAwemeId(awemeId)
    setActiveTab('data')
  }

  const openHealth = () => {
    setOpsTarget((current) => ({ section: 'health', token: current.token + 1 }))
    setActiveTab('ops')
  }

  return (
    <div className="flex flex-col min-h-screen cyber-grid relative">
      {/* License Disclaimer Modal - Shows first or when triggered */}
      {!licenseAccepted && (
        <LicenseDisclaimer onAccept={handleLicenseAccept} />
      )}

      {/* Environment Check Modal - Shows after license accepted */}
      {licenseAccepted && !envChecked && (
        <EnvironmentCheck onCheckComplete={handleEnvCheckComplete} />
      )}

      {/* Header Bar */}
      <Sidebar />
      <GlobalStatusBar
        onOpenOverview={() => setActiveTab('overview')}
        onOpenHealth={openHealth}
        onOpenPending={() => openTasks('pending')}
        onOpenAlerts={() => openAlerts()}
        onOpenSnapshot={() => openTasks('pending')}
      />

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-1 flex-col gap-3 p-2 pb-14 sm:p-3 min-h-0">
        <TabsList className="h-auto w-full max-w-full justify-start overflow-x-auto p-1 sm:w-fit">
          <TabsTrigger value="overview" className="shrink-0 gap-2">
            <LayoutDashboard className="w-4 h-4" />
            {t('tabs.overview')}
          </TabsTrigger>
          <TabsTrigger value="data" className="shrink-0 gap-2">
            <BarChart3 className="w-4 h-4" />
            {t('tabs.monitorData')}
          </TabsTrigger>
          <TabsTrigger value="ops" className="shrink-0 gap-2">
            <Activity className="w-4 h-4" />
            {t('tabs.ops')}
          </TabsTrigger>
          <TabsTrigger value="export" className="shrink-0 gap-2">
            <Download className="w-4 h-4" />
            {t('tabs.export')}
          </TabsTrigger>
          <TabsTrigger value="config" className="shrink-0 gap-2">
            <Settings2 className="w-4 h-4" />
            {t('tabs.config')}
          </TabsTrigger>
        </TabsList>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-12">
          {activeTab === 'overview' && (
            <div className="md:col-span-2 xl:col-span-12">
              <MonitorOverview onOpenTasks={openTasks} onOpenAlerts={openAlerts} onOpenData={openData} />
            </div>
          )}
          {activeTab === 'config' && (
            <div className="md:col-span-2 xl:col-span-12"><CrawlerConfigPanel /></div>
          )}
          {activeTab === 'data' && (
            <div className="md:col-span-2 xl:col-span-12"><MonitorDataCenter focusAwemeId={dataFocusAwemeId} /></div>
          )}
          {activeTab === 'ops' && (
            <div className="md:col-span-2 xl:col-span-12"><MonitorOpsCenter target={opsTarget} /></div>
          )}
          {activeTab === 'export' && (
            <div className="md:col-span-2 xl:col-span-12"><MonitorExport /></div>
          )}
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
