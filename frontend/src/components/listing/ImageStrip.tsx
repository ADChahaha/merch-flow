import { IconPlus, IconX } from '../Icons'

type Props = {
  images: string[]
  onRemove: (src: string) => void
  onInsert: (src: string) => void
  label?: string
  hint?: string
  compact?: boolean
}

/** 图片列表：可删、可插（贴 URL），第一张就是主图时会给个角标。 */
export function ImageStrip({ images, onRemove, onInsert, label, hint, compact }: Props) {
  const size = compact ? 'h-12 w-12' : 'h-20 w-20'

  const insert = () => {
    const url = window.prompt('插入图片 URL')
    if (url && url.trim()) onInsert(url.trim())
  }

  return (
    <div>
      {label && <p className="mb-1.5 text-[11px] text-slate-500">{label}</p>}
      <div className="flex flex-wrap gap-2">
        {images.map((src, index) => (
          <div key={`${src}-${index}`} className={`group relative ${size} overflow-hidden rounded-md ring-1 ring-slate-200`}>
            <img src={src} alt="" className="h-full w-full object-cover" />
            <button
              type="button"
              title="删除"
              onClick={() => onRemove(src)}
              className="absolute top-0.5 right-0.5 rounded bg-black/55 p-0.5 text-white opacity-0 transition group-hover:opacity-100"
            >
              <IconX size={11} />
            </button>
            {index === 0 && !compact && (
              <span className="absolute bottom-0 left-0 rounded-tr bg-brand-600/90 px-1 text-[9px] text-white">
                主图
              </span>
            )}
          </div>
        ))}
        <button
          type="button"
          onClick={insert}
          className={`flex ${size} flex-col items-center justify-center gap-0.5 rounded-md border border-dashed border-slate-300 text-[10px] text-slate-400 transition hover:border-brand-400 hover:text-brand-500`}
        >
          <IconPlus size={14} />
          插入
        </button>
      </div>
      {hint && <p className="mt-1 text-[10px] leading-relaxed text-slate-400">{hint}</p>}
    </div>
  )
}
