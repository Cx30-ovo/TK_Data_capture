# MediaCrawler WebUI Brand Guidelines

## Product Identity

MediaCrawler WebUI is a real-time Douyin account monitoring workspace for media operations teams. The interface should feel:

- Calm and professional
- Data-dense but readable
- Fast to scan during daily monitoring work
- Light-first, with a restrained technical accent
- Operational rather than decorative

## Visual Signature

- Primary action color: TikTok red `#FE2C55`
- Strong action color: `#D91A3F`
- Technical accent: cyan `#25F4EE`
- Primary UI color: blue `#2563EB`
- Background: cool neutral gray
- Surfaces: white cards with light borders and minimal shadow
- Radius: 8px by default, 12px only for large containers

## Voice

- Use direct, operational labels.
- Prefer "开始爬虫", "重新分析", "查看任务" over abstract descriptions.
- Error messages must state the cause and recovery path.
- Avoid technical implementation language in user-facing copy.

## Forbidden Patterns

- No emojis used as interface icons
- No neon glow stacks
- No scanline or decorative moving background
- No oversized hero sections inside the internal tool
- No raw hex colors in page components
- No text smaller than 12px for meaningful content
- No color-only status communication

## Accessibility

- Normal text contrast must be at least 4.5:1
- Keyboard focus must remain visible
- Every action must be reachable without a mouse
- Motion must respect `prefers-reduced-motion`
- Charts must provide text summaries or table alternatives
