import { IconExternal } from './Icons'

/**
 * 原始页面（iframe）：核对 AI 抽取结果用。
 * 禁嵌站点（X-Frame-Options）会白屏，所以永远留一个「打开」出口。
 */
export function SourceFrame({ url, title }: { url: string; title?: string }) {
  return (
    <aside className="hidden min-h-0 w-[42%] min-w-[360px] max-w-[760px] shrink-0 flex-col border-r border-slate-200 bg-white lg:flex">
      <header className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <h2 className="shrink-0 text-[13px] font-semibold text-slate-800">原始页面</h2>
        <span className="min-w-0 flex-1 truncate text-[10px] text-slate-400" title={url}>
          {url}
        </span>
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="flex shrink-0 items-center gap-0.5 text-[11px] text-brand-600 hover:underline"
        >
          <IconExternal size={12} />
          打开
        </a>
      </header>
      <iframe
        key={url}
        src={url}
        title={title || '原始页面'}
        referrerPolicy="no-referrer"
        className="min-h-0 w-full flex-1 border-0 bg-white"
      />
      <p className="border-t border-slate-100 px-3 py-1.5 text-[10px] text-slate-300">
        用于核对抽取结果；禁嵌站点白屏时点「打开」看新标签页
      </p>
    </aside>
  )
}
