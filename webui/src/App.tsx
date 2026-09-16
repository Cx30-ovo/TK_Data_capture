import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Toaster } from 'sonner'
import { BarChart3, LayoutDashboard, ListChecks, Settings2, TerminalSquare } from 'lucide-react'
import { Sidebar } from '@/components/layout/Sidebar'
import { MainContent } from '@/components/layout/MainContent'
import { CrawlerConfigPanel } from '@/components/config/CrawlerConfigPanel'
import { MonitorOverview } from '@/components/monitor/MonitorOverview'
import { MonitorDashboard } from '@/components/monitor/MonitorDashboard'
import { MonitorTasks } from '@/components/monitor/MonitorTasks'
import { EnvironmentCheck, isEnvChecked } from '@/components/env/EnvironmentCheck'
import { LicenseDisclaimer, isLicenseAccepted } from '@/components/license/LicenseDisclaimer'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'

function App() {
  const { t } = useTranslation('common')
  const [activeTab, setActiveTab] = useState('overview')
  // Initialize by checking localStorage if license has been accepted
  const [licenseAccepted, setLicenseAccepted] = useState(() => isLicenseAccepted())
  // Initialize by checking localStorage if env check has passed
  const [envChecked, setEnvChecked] = useState(() => isEnvChecked())
  // State for showing disclaimer manually
  const [showDisclaimer, setShowDisclaimer] = useState(false)

  const handleEnvCheckComplete = () => {
    setEnvChecked(true)
  }

  const handleLicenseAccept = () => {
    setLicenseAccepted(true)
    setShowDisclaimer(false)
  }

  const handleShowDisclaimer = () => {
    setShowDisclaimer(true)
  }

  return (
    <div className="flex flex-col min-h-screen cyber-grid relative">
      {/* License Disclaimer Modal - Shows first or when triggered */}
      {(!licenseAccepted || showDisclaimer) && (
        <LicenseDisclaimer onAccept={handleLicenseAccept} />
      )}

      {/* Environment Check Modal - Shows after license accepted */}
      {licenseAccepted && !showDisclaimer && !envChecked && (
        <EnvironmentCheck onCheckComplete={handleEnvCheckComplete} />
      )}

      {/* Header Bar */}
      <Sidebar onShowDisclaimer={handleShowDisclaimer} />

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col gap-3 p-3 min-h-0">
        <TabsList className="w-fit max-w-full flex-wrap h-auto">
          <TabsTrigger value="overview" className="gap-2">
            <LayoutDashboard className="w-4 h-4" />
            {t('tabs.overview')}
          </TabsTrigger>
          <TabsTrigger value="config" className="gap-2">
            <Settings2 className="w-4 h-4" />
            {t('tabs.config')}
          </TabsTrigger>
          <TabsTrigger value="analytics" className="gap-2">
            <BarChart3 className="w-4 h-4" />
            {t('tabs.analytics')}
          </TabsTrigger>
          <TabsTrigger value="tasks" className="gap-2">
            <ListChecks className="w-4 h-4" />
            {t('tabs.tasks')}
          </TabsTrigger>
          <TabsTrigger value="console" className="gap-2">
            <TerminalSquare className="w-4 h-4" />
            {t('tabs.console')}
          </TabsTrigger>
        </TabsList>

        {activeTab === 'overview' && <MonitorOverview />}
        {activeTab === 'config' && <CrawlerConfigPanel />}
        {activeTab === 'analytics' && <MonitorDashboard />}
        {activeTab === 'tasks' && <MonitorTasks />}
        <div className={activeTab === 'console' ? 'flex flex-col min-h-0' : 'hidden'}>
          <MainContent />
        </div>
      </Tabs>

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
