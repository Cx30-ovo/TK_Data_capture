import { useEffect, useRef, useState } from 'react'
import { Activity, ArrowUpRight, BarChart3, Download, Moon, MoreHorizontal, Radar, Search, Settings2, Sun, UsersRound, X } from 'lucide-react'
import { useThemeStore } from '@/store/themeStore'
import { useCrawlerStatus } from '@/hooks/useCrawler'
import { MonitorAccountSelector } from '@/components/monitor/MonitorAccountSelector'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { LanguageSwitch } from './LanguageSwitch'

export type AppTab = 'insights' | 'overview' | 'accounts' | 'topic-monitor' | 'data' | 'hot' | 'ops' | 'export' | 'config'

const pages: { id: AppTab; label: string; description: string; icon: typeof Radar }[] = [
  { id: 'insights', label: '热点洞察', description: '日期回看、内容线索与空间星云', icon: Radar },
  { id: 'data', label: '内容工作台', description: '作品数据、生命周期与 AI 标题策略', icon: BarChart3 },
  { id: 'topic-monitor', label: '话题监控', description: '关键词、话题采集与高热度作品', icon: Radar },
  { id: 'accounts', label: '账号矩阵', description: '自有账号、竞品账号与风格画像', icon: UsersRound },
  { id: 'overview', label: '运行总览', description: '采集动态、快照与异常记录', icon: Activity },
  { id: 'hot', label: '平台热榜', description: '抖音平台热度信号与原始搜索', icon: Radar },
  { id: 'ops', label: '任务中心', description: '采集任务、告警与运行健康', icon: Activity },
  { id: 'export', label: '数据导出', description: '导出作品数据与监测报告', icon: Download },
  { id: 'config', label: '采集设置', description: '账号接入、采集参数与模型配置', icon: Settings2 },
]

export function SpatialHeader({ activeTab, onNavigate, onSearch }: { activeTab: AppTab; onNavigate: (tab: AppTab) => void; onSearch: (value: string) => void }) {
  useCrawlerStatus()
  const { resolvedTheme, setTheme } = useThemeStore()
  const [query, setQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [toolsOpen, setToolsOpen] = useState(false)
  const toolsRef = useRef<HTMLDivElement>(null)
  const toolsTrigger = useRef<HTMLButtonElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const searchTrigger = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const close = (event: PointerEvent) => { if (!toolsRef.current?.contains(event.target as Node)) setToolsOpen(false) }
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setSearchOpen(true) }
      if (event.key === 'Escape' && toolsOpen) { setToolsOpen(false); toolsTrigger.current?.focus() }
    }
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('pointerdown', close); document.removeEventListener('keydown', key) }
  }, [toolsOpen])
  useEffect(() => { if (toolsOpen) toolsRef.current?.querySelector<HTMLButtonElement>('#spatial-tools-menu button')?.focus() }, [toolsOpen])
  const navigate = (id: AppTab) => { onNavigate(id); setSearchOpen(false); setToolsOpen(false) }
  const results = pages.filter(page => !query.trim() || `${page.label}${page.description}`.includes(query.trim()))
  return <>
    <header className="spatial-header">
      <button className="spatial-brand" onClick={() => navigate('insights')} aria-label="首页">
        <Radar aria-hidden="true" />
      </button>
      <button ref={searchTrigger} className="spatial-search-trigger" aria-label="搜索内容与功能" onClick={() => setSearchOpen(true)}><Search aria-hidden="true" /><span>搜索内容与功能</span><kbd>Ctrl K</kbd></button>
      <div className="spatial-theme" role="group" aria-label="界面配色">
        <button aria-pressed={resolvedTheme === 'dark'} onClick={() => setTheme('dark')}><Moon aria-hidden="true" />深色</button>
        <button aria-pressed={resolvedTheme === 'light'} onClick={() => setTheme('light')}><Sun aria-hidden="true" />浅色</button>
      </div>
      <nav className="spatial-main-nav" aria-label="主导航">{pages.slice(0, 4).map(page => <button key={page.id} aria-current={activeTab === page.id ? 'page' : undefined} onClick={() => navigate(page.id)}>{page.label}</button>)}</nav>
      <div ref={toolsRef} className="spatial-tools">
        <button ref={toolsTrigger} className="spatial-icon-button" aria-label="更多功能" aria-expanded={toolsOpen} aria-controls="spatial-tools-menu" onClick={() => setToolsOpen(!toolsOpen)}><MoreHorizontal aria-hidden="true" /></button>
        {toolsOpen && <div className="spatial-tools-menu" id="spatial-tools-menu"><p>监测与管理</p>{pages.slice(4).map(page => <button key={page.id} aria-current={activeTab === page.id ? 'page' : undefined} onClick={() => navigate(page.id)}><page.icon aria-hidden="true" />{page.label}<ArrowUpRight aria-hidden="true" /></button>)}<LanguageSwitch /></div>}
      </div>
    </header>
    <div className="spatial-context"><span className="spatial-context-label"><span className="spatial-live-dot" />内容情报编辑台</span><div className="spatial-account"><MonitorAccountSelector /></div><button onClick={() => navigate('config')}><Settings2 aria-hidden="true" />管理采集</button></div>
    <Dialog open={searchOpen} onOpenChange={setSearchOpen}><DialogContent className="spatial-command" onCloseAutoFocus={event => { event.preventDefault(); searchTrigger.current?.focus() }}><DialogTitle>搜索内容与功能</DialogTitle><DialogDescription>查找模块，或搜索当前账号已采集的内容。</DialogDescription><form onSubmit={event => { event.preventDefault(); if (query.trim()) { onSearch(query.trim()); setSearchOpen(false) } }}><label className="spatial-command-input"><Search aria-hidden="true" /><input autoFocus ref={searchRef} value={query} onChange={event => setQuery(event.target.value)} placeholder="输入关键词…" aria-label="搜索内容与功能" />{query && <button type="button" aria-label="清空搜索" onClick={() => setQuery('')}><X aria-hidden="true" /></button>}</label>{query.trim() && <button className="spatial-command-result" type="submit"><Search aria-hidden="true" /><span>在内容线索中搜索「{query.trim()}」</span><ArrowUpRight aria-hidden="true" /></button>}</form><div className="spatial-command-results">{results.map(page => <button key={page.id} className="spatial-command-result" onClick={() => navigate(page.id)}><page.icon aria-hidden="true" /><span><strong>{page.label}</strong><small>{page.description}</small></span><ArrowUpRight aria-hidden="true" /></button>)}</div></DialogContent></Dialog>
  </>
}
