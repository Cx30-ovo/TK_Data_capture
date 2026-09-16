import type { ComponentType, ReactNode, KeyboardEvent } from 'react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Clock3, Database, Globe, HardDrive, KeyRound, Play, Save, ShieldAlert, Square, X } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { useCrawlerStore } from '@/store/crawlerStore'
import { usePlatforms, useConfigOptions, useStartCrawler, useStopCrawler } from '@/hooks/useCrawler'
import { monitorApi, schedulerApi } from '@/lib/api'
import { MonitorPanel } from '@/components/monitor/MonitorPanel'
import { ParsedIdList } from './ParsedIdList'


type SectionProps = {
  title: string
  description: string
  icon: ComponentType<{ className?: string }>
  children: ReactNode
}

function Section({ title, description, icon: Icon, children }: SectionProps) {
  return (
    <section className="rounded-lg glass-panel float-panel overflow-hidden">
      <header className="flex items-center gap-3 border-b border-cyber-border-subtle/50 bg-cyber-bg-tertiary/30 px-4 py-3">
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary">
          <Icon className="h-4 w-4 text-cyber-neon-cyan" />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-mono font-semibold tracking-wide text-cyber-text-primary">{title}</div>
          <div className="truncate text-[10px] leading-snug text-cyber-text-muted">{description}</div>
        </div>
      </header>
      <div className="space-y-4 p-4">{children}</div>
    </section>
  )
}

function ValueHint({ current, recommended }: { current: string; recommended: string }) {
  const { t } = useTranslation('config')
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[9px] font-mono text-cyber-text-muted">
      <span>{t('configCenter.current')}: <span className="text-cyber-text-secondary">{current}</span></span>
      <span>{t('configCenter.recommended')}: <span className="text-cyber-neon-green">{recommended}</span></span>
    </div>
  )
}

type FieldProps = {
  label: string
  hint?: string
  children: ReactNode
}

function Field({ label, hint, children }: FieldProps) {
  return (
    <div className="space-y-2">
      <div className="space-y-0.5">
        <Label className="text-xs font-mono text-cyber-text-secondary">{label}</Label>
        {hint ? <p className="text-[10px] leading-snug text-cyber-text-muted">{hint}</p> : null}
      </div>
      {children}
    </div>
  )
}

type KeywordInputProps = {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
}

function KeywordInput({ value, onChange, placeholder, disabled }: KeywordInputProps) {
  const [inputValue, setInputValue] = useState('')
  const keywords = value ? value.split(',').map((keyword) => keyword.trim()).filter(Boolean) : []

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return
    event.preventDefault()
    const trimmed = inputValue.trim()
    if (trimmed && !keywords.includes(trimmed)) {
      onChange([...keywords, trimmed].join(','))
      setInputValue('')
    }
  }

  return (
    <div className="space-y-2">
      <Input value={inputValue} onChange={(event) => setInputValue(event.target.value)} onKeyDown={handleKeyDown} placeholder={placeholder} disabled={disabled} className="h-9 text-xs" />
      {keywords.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {keywords.map((keyword) => (
            <span key={keyword} className="inline-flex items-center gap-1 rounded-md border border-cyber-neon-cyan/30 bg-cyber-neon-cyan/10 px-2 py-1 text-xs font-mono text-cyber-neon-cyan">
              {keyword}
              {!disabled ? <button type="button" onClick={() => onChange(keywords.filter((item) => item !== keyword).join(','))}><X className="h-3 w-3" /></button> : null}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function MaintenanceRow({ label, current, recommended }: { label: string; current: string; recommended: string }) {
  return (
    <div className="grid grid-cols-[minmax(120px,1fr)_minmax(90px,1fr)_minmax(90px,1fr)] items-center gap-3 border-b border-cyber-border-subtle/40 px-3 py-2.5 last:border-b-0">
      <div className="text-[11px] font-mono text-cyber-text-primary">{label}</div>
      <div className="text-[10px] font-mono text-cyber-text-secondary">{current}</div>
      <div className="text-[10px] font-mono text-cyber-neon-green">{recommended}</div>
    </div>
  )
}


export function CrawlerConfigPanel() {
  const { t } = useTranslation('config')
  const config = useCrawlerStore((state) => state.config)
  const savedConfig = useCrawlerStore((state) => state.savedConfig)
  const updateConfig = useCrawlerStore((state) => state.updateConfig)
  const saveConfig = useCrawlerStore((state) => state.saveConfig)
  const status = useCrawlerStore((state) => state.status)
  const { data: platforms } = usePlatforms()
  const { data: options } = useConfigOptions()
  const { mutate: startCrawler, isPending: isStarting } = useStartCrawler()
  const { mutate: stopCrawler, isPending: isStopping } = useStopCrawler()
  const queryClient = useQueryClient()
  const { data: schedulerStatus } = useQuery({
    queryKey: ['schedulerStatus'],
    queryFn: async () => (await schedulerApi.getStatus()).data,
    refetchInterval: 30000,
  })
  const { data: health } = useQuery({
    queryKey: ['monitorHealth'],
    queryFn: async () => (await monitorApi.getHealth()).data,
    refetchInterval: 30000,
  })
  const [scheduleEnabled, setScheduleEnabled] = useState(false)
  const [scheduleTimesText, setScheduleTimesText] = useState('')
  const [savedSchedule, setSavedSchedule] = useState({ enabled: false, timesText: '' })
  const [monitorDirty, setMonitorDirty] = useState(false)
  const [monitorValid, setMonitorValid] = useState(true)
  const [dangerAction, setDangerAction] = useState<'stop' | 'disable-schedule' | null>(null)
  const monitorSaveHandlerRef = useRef<(() => void) | null>(null)
  const scheduleInitializedRef = useRef(false)

  const saveSchedule = useMutation({
    mutationFn: () => schedulerApi.update({
      enabled: scheduleEnabled,
      times: scheduleTimesText.split(/[,，\s]+/).map((value) => value.trim()).filter(Boolean),
      crawler: config,
    }),
    onSuccess: (response) => {
      toast.success(t('schedule.saved'))
      setSavedSchedule({ enabled: scheduleEnabled, timesText: scheduleTimesText })
      queryClient.setQueryData(['schedulerStatus'], response.data)
    },
    onError: (error: Error) => toast.error(`${t('schedule.failed')}: ${error.message}`),
  })
  const disableSchedule = useMutation({
    mutationFn: () => schedulerApi.disable(),
    onSuccess: (response) => {
      toast.success(t('configCenter.scheduleDisabled'))
      setScheduleEnabled(false)
      setSavedSchedule({ enabled: false, timesText: scheduleTimesText })
      queryClient.setQueryData(['schedulerStatus'], response.data)
      setDangerAction(null)
    },
    onError: (error: Error) => toast.error(`${t('configCenter.dangerFailed')}: ${error.message}`),
  })

  useEffect(() => {
    if (config.platform !== 'dy') updateConfig({ platform: 'dy' })
  }, [config.platform, updateConfig])

  const scheduleTimes = scheduleTimesText.split(/[,，\s]+/).map((value) => value.trim()).filter(Boolean)
  const invalidScheduleTimes = scheduleTimes.filter((value) => !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value))
  const scheduleInvalid = scheduleEnabled && (scheduleTimes.length === 0 || invalidScheduleTimes.length > 0)
  const scheduleDirty = scheduleEnabled !== savedSchedule.enabled || scheduleTimesText.trim() !== savedSchedule.timesText.trim()

  useEffect(() => {
    if (!schedulerStatus) return
    if (scheduleInitializedRef.current && scheduleDirty) return
    const timesText = schedulerStatus.times.join(', ')
    setScheduleEnabled(schedulerStatus.enabled)
    setScheduleTimesText(timesText)
    setSavedSchedule({ enabled: schedulerStatus.enabled, timesText })
    scheduleInitializedRef.current = true
  }, [schedulerStatus, scheduleDirty])

  const configDirty = JSON.stringify(config) !== JSON.stringify(savedConfig)
  const anyDirty = configDirty || scheduleDirty || monitorDirty
  const isDisabled = status === 'running' || status === 'stopping'
  const isRunning = status === 'running'
  const isBusy = isStarting || isStopping || status === 'stopping' || saveSchedule.isPending || disableSchedule.isPending
  const platformOptions = (platforms || []).filter((platform) => platform.value === 'dy')

  const handleSaveAll = () => {
    if (configDirty) {
      saveConfig()
      toast.success(t('configCenter.configSaved'))
    }
    if (monitorDirty) monitorSaveHandlerRef.current?.()
    if (scheduleDirty) saveSchedule.mutate()
  }

  const runDangerAction = () => {
    if (dangerAction === 'stop') {
      stopCrawler()
      setDangerAction(null)
    }
    if (dangerAction === 'disable-schedule') disableSchedule.mutate()
  }

  return (
    <div className="space-y-3 animate-slide-up">
      <section className="sticky top-12 z-10 rounded-lg border border-cyber-border-subtle bg-cyber-bg-panel/95 p-2 shadow-[0_4px_16px_rgba(15,23,42,0.08)] backdrop-blur">
        <div className="flex flex-wrap items-center gap-2">
          <div className="px-1 text-[10px] font-mono text-cyber-text-muted">{t('configCenter.title')}</div>
          <span className={`rounded border px-2 py-1 text-[9px] font-mono ${anyDirty ? 'border-cyber-neon-orange/40 bg-cyber-neon-orange/5 text-cyber-neon-orange' : 'border-cyber-neon-green/30 bg-cyber-neon-green/5 text-cyber-neon-green'}`}>
            {anyDirty ? t('configCenter.unsaved') : t('configCenter.saved')}
          </span>
          <Button
            type="button"
            variant={anyDirty ? 'default' : 'outline'}
            size="sm"
            onClick={handleSaveAll}
            disabled={!anyDirty || scheduleInvalid || (monitorDirty && !monitorValid) || isBusy}
            className="h-8 font-mono text-[10px]"
          >
            <Save className="h-3.5 w-3.5" />
            {t('configCenter.saveAll')}
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => {
              setDangerAction(null)
              startCrawler(config)
            }}
            disabled={isBusy || isRunning || scheduleInvalid}
            className="h-8 font-mono text-[10px]"
          >
            <Play className="h-3.5 w-3.5" />
            {isStarting ? t('button.initiating') : t('button.initiateScan')}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => dangerAction === 'stop' ? runDangerAction() : setDangerAction('stop')}
            disabled={!isRunning || isStopping}
            className="h-8 font-mono text-[10px] text-cyber-neon-pink"
          >
            <Square className="h-3.5 w-3.5" />
            {dangerAction === 'stop' ? t('configCenter.danger.confirmAgain') : t('button.terminate')}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => dangerAction === 'disable-schedule' ? runDangerAction() : setDangerAction('disable-schedule')}
            disabled={!scheduleEnabled || disableSchedule.isPending}
            className="h-8 font-mono text-[10px] text-cyber-neon-orange"
          >
            <Clock3 className="h-3.5 w-3.5" />
            {dangerAction === 'disable-schedule' ? t('configCenter.danger.confirmAgain') : t('configCenter.danger.disableSchedule')}
          </Button>
          <span className="ml-auto hidden text-[9px] font-mono text-cyber-text-muted xl:inline">{t('configCenter.saveHint')}</span>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
      <Section title={t('configCenter.sections.monitorAccount')} description={t('configCenter.sections.monitorAccountHint')} icon={Globe}>
        <MonitorPanel
          embedded
          onDirtyChange={setMonitorDirty}
          onValidChange={setMonitorValid}
          saveHandlerRef={monitorSaveHandlerRef}
        />
        <ValueHint current={t('configCenter.values.monitorCurrent')} recommended={t('configCenter.values.monitorRecommended')} />
      </Section>

      <Section title={t('configCenter.sections.collectionRange')} description={t('configCenter.sections.collectionRangeHint')} icon={Database}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Field label={t('field.platform')}>
            <Select value="dy" disabled>
              <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>{platformOptions.map((platform) => <SelectItem key={platform.value} value={platform.value}>{platform.label}</SelectItem>)}</SelectContent>
            </Select>
            <ValueHint current="抖音" recommended="抖音" />
          </Field>
          <Field label={t('field.crawlType')}>
            <Select value={config.crawler_type} onValueChange={(value) => updateConfig({ crawler_type: value })} disabled={isDisabled}>
              <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>{options?.crawler_types.map((type) => <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>)}</SelectContent>
            </Select>
            <ValueHint current={config.crawler_type} recommended="creator" />
          </Field>
          <Field label={t('field.startPage')}>
            <Input type="number" min={1} value={config.start_page} onChange={(event) => updateConfig({ start_page: parseInt(event.target.value) || 1 })} disabled={isDisabled} className="h-9 text-xs" />
            <ValueHint current={String(config.start_page)} recommended="1" />
          </Field>
        </div>

        <Field label={t('field.timeRange')} hint={t('field.timeRangeHint')}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Input type="date" value={config.start_time || ''} onChange={(event) => updateConfig({ start_time: event.target.value })} disabled={isDisabled} className="h-9 text-xs" />
            <Input type="date" value={config.end_time || ''} onChange={(event) => updateConfig({ end_time: event.target.value })} disabled={isDisabled} className="h-9 text-xs" />
          </div>
          <ValueHint current={`${config.start_time || '-'} ~ ${config.end_time || '-'}`} recommended={t('configCenter.values.unlimited')} />
        </Field>

        {config.crawler_type === 'search' ? <Field label={t('field.keywords')} hint={t('field.keywordsHint')}><KeywordInput value={config.keywords} onChange={(keywords) => updateConfig({ keywords })} disabled={isDisabled} placeholder={t('field.keywordsPlaceholder')} /></Field> : null}
        {config.crawler_type === 'detail' ? <Field label={t('field.specifiedIds')} hint={t('field.specifiedIdsHint')}><textarea value={config.specified_ids} onChange={(event) => updateConfig({ specified_ids: event.target.value })} disabled={isDisabled} className="min-h-[72px] w-full rounded-md border border-cyber-border-DEFAULT bg-cyber-bg-tertiary px-3 py-2 text-xs font-mono text-cyber-text-primary" /><ParsedIdList value={config.specified_ids} platform="dy" type="detail" disabled={isDisabled} /></Field> : null}
        {config.crawler_type === 'creator' ? <Field label={t('field.creatorIds')} hint={t('field.creatorIdsHint')}><textarea value={config.creator_ids} onChange={(event) => updateConfig({ creator_ids: event.target.value })} disabled={isDisabled} className="min-h-[72px] w-full rounded-md border border-cyber-border-DEFAULT bg-cyber-bg-tertiary px-3 py-2 text-xs font-mono text-cyber-text-primary" /><ParsedIdList value={config.creator_ids} platform="dy" type="creator" disabled={isDisabled} /></Field> : null}
      </Section>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
      <Section title={t('configCenter.sections.runtimeStrategy')} description={t('configCenter.sections.runtimeStrategyHint')} icon={KeyRound}>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label={t('field.loginMethod')}>
            <Select value={config.login_type} onValueChange={(value) => updateConfig({ login_type: value })} disabled={isDisabled}>
              <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>{options?.login_types.map((type) => <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>)}</SelectContent>
            </Select>
            <ValueHint current={config.login_type} recommended="qrcode" />
          </Field>
          <Field label={t('field.saveFormat')}>
            <Select value={config.save_option} onValueChange={(value) => updateConfig({ save_option: value })} disabled={isDisabled}>
              <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>{options?.save_options.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
            </Select>
            <ValueHint current={config.save_option} recommended="sqlite" />
          </Field>
        </div>
        {config.login_type === 'cookie' ? <Field label={t('field.cookies')} hint={t('field.cookiesHint')}><textarea value={config.cookies} onChange={(event) => updateConfig({ cookies: event.target.value })} disabled={isDisabled} className="min-h-[72px] w-full rounded-md border border-cyber-border-DEFAULT bg-cyber-bg-tertiary px-3 py-2 text-xs font-mono text-cyber-text-primary" /></Field> : null}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {[
            { checked: config.enable_comments, label: t('field.commentExtraction'), onChange: (checked: boolean) => updateConfig({ enable_comments: checked, enable_sub_comments: checked ? config.enable_sub_comments : false }) },
            { checked: config.enable_sub_comments, label: t('field.subComments'), disabled: !config.enable_comments, onChange: (checked: boolean) => updateConfig({ enable_sub_comments: checked }) },
            { checked: config.headless, label: t('field.headlessMode'), onChange: (checked: boolean) => updateConfig({ headless: checked }) },
          ].map((item) => (
            <label key={item.label} className="flex items-center gap-3 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-2.5">
              <Checkbox checked={item.checked} onCheckedChange={(checked) => item.onChange(checked === true)} disabled={isDisabled || item.disabled} />
              <span className="text-[11px] font-mono text-cyber-text-primary">{item.label}</span>
            </label>
          ))}
        </div>

        <div className="grid grid-cols-1 gap-3 border-t border-cyber-border-subtle/50 pt-4 md:grid-cols-[220px_1fr]">
          <div className="flex items-center gap-3 rounded-md border border-cyber-border-subtle bg-cyber-bg-tertiary/20 p-3">
            <Checkbox checked={scheduleEnabled} onCheckedChange={(checked) => setScheduleEnabled(checked === true)} disabled={isDisabled || saveSchedule.isPending} />
            <div><div className="text-xs font-mono text-cyber-text-primary">{t('schedule.enable')}</div><div className="mt-0.5 text-[9px] font-mono text-cyber-text-muted">{schedulerStatus?.next_run_at ? new Date(schedulerStatus.next_run_at).toLocaleString() : t('schedule.never')}</div></div>
          </div>
          <Field label={t('schedule.times')} hint={t('schedule.timesHint')}>
            <div className="flex items-center gap-2"><Clock3 className="h-4 w-4 text-cyber-text-muted" /><Input value={scheduleTimesText} onChange={(event) => setScheduleTimesText(event.target.value)} placeholder="14:00, 18:00" disabled={isDisabled || !scheduleEnabled} className="h-9 text-xs font-mono" /></div>
            {invalidScheduleTimes.length > 0 ? <p className="text-[10px] font-mono text-cyber-neon-orange">{t('schedule.invalid')}: {invalidScheduleTimes.join(', ')}</p> : null}
            <ValueHint current={scheduleTimesText || '-'} recommended="14:00, 18:00" />
          </Field>
        </div>
      </Section>

      <Section title={t('configCenter.sections.systemMaintenance')} description={t('configCenter.sections.systemMaintenanceHint')} icon={HardDrive}>
        <div className="flex items-start gap-2 rounded-md border border-cyber-neon-cyan/25 bg-cyber-neon-cyan/5 p-3 text-[10px] font-mono text-cyber-text-muted">
          <ShieldAlert className="mt-0.5 h-4 w-4 flex-shrink-0 text-cyber-neon-cyan" />
          {t('configCenter.maintenanceReadOnly')}
        </div>
        <div className="overflow-hidden rounded-md border border-cyber-border-subtle">
          <div className="grid grid-cols-[minmax(120px,1fr)_minmax(90px,1fr)_minmax(90px,1fr)] gap-3 bg-cyber-bg-tertiary/40 px-3 py-2 text-[9px] font-mono text-cyber-text-muted">
            <span>{t('configCenter.parameter')}</span><span>{t('configCenter.current')}</span><span>{t('configCenter.recommended')}</span>
          </div>
          <MaintenanceRow label={t('configCenter.maintenance.autoBackup')} current={health?.system_config?.auto_backup ? t('configCenter.on') : t('configCenter.off')} recommended={t('configCenter.on')} />
          <MaintenanceRow label={t('configCenter.maintenance.backupInterval')} current={`${health?.system_config?.backup_interval_hours ?? '-'} h`} recommended="6 h" />
          <MaintenanceRow label={t('configCenter.maintenance.backupRetention')} current={`${health?.system_config?.backup_retention_days ?? '-'} d`} recommended="14 d" />
          <MaintenanceRow label={t('configCenter.maintenance.logRetention')} current={`${health?.system_config?.log_retention_days ?? '-'} d`} recommended="14 d" />
          <MaintenanceRow label={t('configCenter.maintenance.startBrowser')} current={health?.system_config?.start_browser_on_service_start ? t('configCenter.on') : t('configCenter.off')} recommended={t('configCenter.on')} />
          <MaintenanceRow label={t('configCenter.maintenance.cdpPort')} current={String(health?.system_config?.cdp_debug_port ?? '-')} recommended="9222" />
        </div>
      </Section>
      </div>

    </div>
  )
}
