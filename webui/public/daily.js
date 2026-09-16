(() => {
  const API = '/api/monitor'
  const dateInput = document.getElementById('reportDate')
  const statusText = document.getElementById('dailyStatus')
  const lead = document.getElementById('dailyLead')
  const hotList = document.getElementById('hotList')
  const categories = document.getElementById('dailyCategories')
  const feed = document.getElementById('dailyFeed')
  const feedSummary = document.getElementById('feedSummary')
  const quickStats = document.getElementById('quickStats')
  const activity = document.getElementById('accountActivity')
  const toast = document.getElementById('dailyToast')

  const state = {
    date: getDateFromQuery(),
    category: 'all',
    dashboard: null,
    jobs: [],
    monitorStatus: null,
  }

  const CATEGORIES = [
    { key: 'all', label: '全部' },
    { key: 'new', label: '当日新增' },
    { key: 'snapshot', label: '有快照更新' },
    { key: 'abnormal', label: '存在异常' },
    { key: 'insufficient', label: '数据不足' },
  ]

  function getDateFromQuery() {
    const queryDate = new URLSearchParams(window.location.search).get('date')
    return /^\d{4}-\d{2}-\d{2}$/.test(queryDate || '') ? queryDate : formatDateKey(new Date())
  }

  function formatDateKey(value) {
    const date = value instanceof Date ? value : new Date(value)
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }

  function timestampDateKey(timestamp) {
    return timestamp ? formatDateKey(new Date(timestamp * 1000)) : ''
  }

  function formatDateTime(timestamp) {
    return timestamp ? new Date(timestamp * 1000).toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>'"]/g, (character) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;',
    }[character]))
  }

  function showToast(message) {
    toast.textContent = message
    toast.classList.add('show')
    window.setTimeout(() => toast.classList.remove('show'), 2600)
  }

  async function fetchJson(path) {
    const response = await fetch(path, { headers: { Accept: 'application/json' } })
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
    return response.json()
  }

  function latestSnapshot(post) {
    return [...(post.snapshots || [])].sort((left, right) => right.actual_age_seconds - left.actual_age_seconds)[0]
  }

  function jobsForPost(awemeId) {
    return state.jobs.filter((job) => job.aweme_id === awemeId)
  }

  function postState(post) {
    const jobs = jobsForPost(post.aweme_id)
    if (jobs.some((job) => job.status === 'failed')) return { key: 'error', label: '存在失败' }
    if (jobs.some((job) => job.status === 'missed')) return { key: 'warning', label: '存在错过' }
    if ((post.snapshots || []).length === 0) return { key: 'info', label: '数据不足' }
    return { key: 'normal', label: '采样正常' }
  }

  function isNewOnDate(post) {
    return timestampDateKey(post.first_seen_at) === state.date
  }

  function hasSnapshotOnDate(post) {
    return (post.snapshots || []).some((snapshot) => timestampDateKey(snapshot.captured_at) === state.date)
  }

  function isAbnormal(post) {
    return jobsForPost(post.aweme_id).some((job) => job.status === 'failed' || job.status === 'missed')
  }

  function dailyPosts() {
    return (state.dashboard?.posts || []).filter((post) => isNewOnDate(post) || hasSnapshotOnDate(post))
  }

  function filterPosts(posts) {
    if (state.category === 'new') return posts.filter(isNewOnDate)
    if (state.category === 'snapshot') return posts.filter(hasSnapshotOnDate)
    if (state.category === 'abnormal') return posts.filter(isAbnormal)
    if (state.category === 'insufficient') return posts.filter((post) => (post.snapshots || []).length === 0)
    return posts
  }

  function renderLead(posts) {
    const leadPost = [...posts].sort((left, right) => (latestSnapshot(right)?.liked_count || 0) - (latestSnapshot(left)?.liked_count || 0))[0]
    if (!leadPost) {
      lead.innerHTML = '<div class="daily-empty">当天没有发现作品或快照更新。</div>'
      return
    }
    const snapshot = latestSnapshot(leadPost)
    const stateInfo = postState(leadPost)
    lead.innerHTML = `
      <div class="lead-copy">
        <p class="lead-kicker">当日主推 · ${escapeHtml(stateInfo.label)}</p>
        <a class="lead-title" href="${escapeHtml(leadPost.canonical_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(leadPost.title || leadPost.aweme_id)}</a>
        <p class="lead-excerpt">${escapeHtml(leadPost.desc || '暂无正文摘要')}</p>
        <p class="lead-meta">首次发现 ${formatDateTime(leadPost.first_seen_at)} · ${(leadPost.snapshots || []).length} 条快照</p>
        <div class="lead-metrics">
          <span class="lead-metric">点赞 ${snapshot?.liked_count || 0}</span>
          <span class="lead-metric">收藏 ${snapshot?.collected_count || 0}</span>
          <span class="lead-metric">评论 ${snapshot?.comment_count || 0}</span>
          <span class="lead-metric">分享 ${snapshot?.share_count || 0}</span>
        </div>
      </div>
      <span class="lead-marker">${escapeHtml(snapshot?.stage || 'first_seen')}</span>
    `
  }

  function renderHot(posts) {
    const ranking = [...posts].sort((left, right) => (latestSnapshot(right)?.liked_count || 0) - (latestSnapshot(left)?.liked_count || 0)).slice(0, 5)
    hotList.innerHTML = ranking.map((post, index) => {
      const snapshot = latestSnapshot(post)
      return `
        <li>
          <span class="hot-rank rank-${index + 1}">${index + 1}</span>
          <span class="hot-main">
            <a class="hot-title" href="${escapeHtml(post.canonical_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(post.title || post.aweme_id)}</a>
            <small>${escapeHtml(snapshot?.stage || 'first_seen')} · ${formatDateTime(snapshot?.captured_at || post.first_seen_at)}</small>
          </span>
          <span class="hot-value">${snapshot?.liked_count || 0}</span>
        </li>
      `
    }).join('') || '<li class="daily-empty">暂无热点数据</li>'
  }

  function categoryCounts(posts) {
    return {
      all: posts.length,
      new: posts.filter(isNewOnDate).length,
      snapshot: posts.filter(hasSnapshotOnDate).length,
      abnormal: posts.filter(isAbnormal).length,
      insufficient: posts.filter((post) => (post.snapshots || []).length === 0).length,
    }
  }

  function renderCategories(posts) {
    const counts = categoryCounts(posts)
    categories.innerHTML = CATEGORIES.map((category) => `
      <button type="button" class="${state.category === category.key ? 'active' : ''}" data-category="${category.key}">
        ${category.label} ${counts[category.key] || 0}
      </button>
    `).join('')
    categories.querySelectorAll('button').forEach((button) => {
      button.addEventListener('click', () => {
        state.category = button.dataset.category
        render()
      })
    })
  }

  function renderFeed(posts) {
    const visible = filterPosts(posts)
    const selectedLabel = CATEGORIES.find((category) => category.key === state.category)?.label || '全部'
    feedSummary.textContent = `${state.date} · ${selectedLabel} · ${visible.length} 篇`
    feed.innerHTML = visible.map((post) => {
      const snapshot = latestSnapshot(post)
      const stateInfo = postState(post)
      return `
        <article class="daily-article">
          <p class="article-account-name">${isNewOnDate(post) ? '当日新增' : '快照更新'}</p>
          <a class="article-title" href="${escapeHtml(post.canonical_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(post.title || post.aweme_id)}</a>
          <p class="article-excerpt">${escapeHtml(post.desc || '暂无正文摘要')}</p>
          <div class="article-stats">
            <span class="article-stat">点赞 ${snapshot?.liked_count || 0}</span>
            <span class="article-stat">收藏 ${snapshot?.collected_count || 0}</span>
            <span class="article-stat">评论 ${snapshot?.comment_count || 0}</span>
            <span class="article-stat">${(post.snapshots || []).length} 条快照</span>
          </div>
          <span class="article-state state-${stateInfo.key}">${stateInfo.label}</span>
          <p class="article-meta">${formatDateTime(post.first_seen_at)} · ${escapeHtml(post.aweme_id)}</p>
        </article>
      `
    }).join('') || '<div class="daily-empty">当前分类没有数据。</div>'
  }

  function renderStats(posts) {
    const snapshotEvents = posts.reduce((count, post) => count + (post.snapshots || []).filter((snapshot) => timestampDateKey(snapshot.captured_at) === state.date).length, 0)
    const problemJobs = state.jobs.filter((job) => timestampDateKey(job.due_at) === state.date && (job.status === 'failed' || job.status === 'missed')).length
    quickStats.innerHTML = `
      <span class="quick-stat">新增 ${posts.filter(isNewOnDate).length}</span>
      <span class="quick-stat">快照事件 ${snapshotEvents}</span>
      <span class="quick-stat">异常任务 ${problemJobs}</span>
    `
  }

  function renderActivity(posts) {
    const account = state.monitorStatus?.account
    const jobsOnDate = state.jobs.filter((job) => timestampDateKey(job.due_at) === state.date || timestampDateKey(job.finished_at) === state.date)
    const snapshotStages = {}
    posts.forEach((post) => (post.snapshots || []).forEach((snapshot) => {
      if (timestampDateKey(snapshot.captured_at) === state.date) snapshotStages[snapshot.stage] = (snapshotStages[snapshot.stage] || 0) + 1
    }))
    const jobStatuses = jobsOnDate.reduce((result, job) => {
      result[job.status] = (result[job.status] || 0) + 1
      return result
    }, {})

    activity.innerHTML = `
      <section class="activity-group">
        <div class="activity-head"><h3>监控账号</h3><span>${account?.sec_user_id ? '已配置' : '未配置'}</span></div>
        <ul><li><a href="${escapeHtml(account?.profile_url || '#')}" target="_blank" rel="noopener noreferrer">${escapeHtml(account?.sec_user_id || '尚未配置监控账号')}</a><time>${account?.last_discovered_at ? formatDateTime(account.last_discovered_at) : '-'}</time></li></ul>
      </section>
      <section class="activity-group">
        <div class="activity-head"><h3>快照阶段</h3><span>${Object.values(snapshotStages).reduce((sum, value) => sum + value, 0)}</span></div>
        <ul>${Object.entries(snapshotStages).map(([stage, count]) => `<li><a href="#">${escapeHtml(stage)}</a><time>${count}</time></li>`).join('') || '<li><a href="#">暂无快照</a><time>0</time></li>'}</ul>
      </section>
      <section class="activity-group">
        <div class="activity-head"><h3>任务状态</h3><span>${jobsOnDate.length}</span></div>
        <ul>${Object.entries(jobStatuses).map(([status, count]) => `<li><a href="#">${escapeHtml(status)}</a><time>${count}</time></li>`).join('') || '<li><a href="#">暂无任务</a><time>0</time></li>'}</ul>
      </section>
    `
  }

  function render() {
    const posts = dailyPosts()
    renderLead(posts)
    renderHot(posts)
    renderCategories(posts)
    renderStats(posts)
    renderFeed(posts)
    renderActivity(posts)
    statusText.textContent = `共读取 ${state.dashboard?.posts?.length || 0} 篇作品 · ${state.jobs.length} 个任务`
  }

  async function load() {
    try {
      statusText.textContent = '正在读取监控数据…'
      const [dashboard, jobData, monitorStatus] = await Promise.all([
        fetchJson(`${API}/dashboard?limit=100`),
        fetchJson(`${API}/jobs?limit=500`),
        fetchJson(`${API}/status`),
      ])
      state.dashboard = dashboard
      state.jobs = jobData.jobs || []
      state.monitorStatus = monitorStatus
      render()
    } catch (error) {
      statusText.textContent = '监控数据加载失败'
      lead.innerHTML = `<div class="daily-empty">无法读取数据：${escapeHtml(error.message)}</div>`
      showToast(`日报加载失败：${error.message}`)
    }
  }

  function moveDate(offset) {
    const date = new Date(`${state.date}T00:00:00`)
    date.setDate(date.getDate() + offset)
    state.date = formatDateKey(date)
    dateInput.value = state.date
    window.history.replaceState(null, '', `/daily.html?date=${state.date}`)
    load()
  }

  dateInput.value = state.date
  dateInput.addEventListener('change', () => {
    if (!dateInput.value) return
    state.date = dateInput.value
    window.history.replaceState(null, '', `/daily.html?date=${state.date}`)
    load()
  })
  document.getElementById('previousDay').addEventListener('click', () => moveDate(-1))
  document.getElementById('nextDay').addEventListener('click', () => moveDate(1))
  load()
})()
