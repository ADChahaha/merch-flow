import { IconBox, IconSettings, IconUpload } from './Icons'

const NAV = [
  { key: 'products', label: '商品', Icon: IconBox },
  { key: 'listing', label: '上架', Icon: IconUpload },
  { key: 'settings', label: '设置', Icon: IconSettings },
]

export function IconRail({
  active = 'products',
  cartCount = 0,
  onSelect,
}: {
  active?: string
  cartCount?: number
  onSelect?: (key: string) => void
}) {
  return (
    <nav className="flex h-full w-16 flex-col items-center gap-1 border-r border-slate-200 bg-white pt-3">
      {NAV.map(({ key, label, Icon }) => {
        const isActive = key === active
        return (
          <button
            key={key}
            type="button"
            onClick={() => onSelect?.(key)}
            className={`flex w-14 flex-col items-center gap-1 rounded-lg px-1 py-2.5 text-[11px] transition ${
              isActive
                ? 'bg-brand-50 font-medium text-brand-700'
                : 'text-slate-400 hover:bg-slate-50 hover:text-slate-600'
            }`}
          >
            <span className="relative">
              <Icon size={20} />
              {key === 'listing' && cartCount > 0 && (
                <span className="absolute -top-1 -right-2 rounded-full bg-rose-500 px-1 text-[9px] leading-4 text-white">
                  {cartCount > 99 ? '99+' : cartCount}
                </span>
              )}
            </span>
            {label}
          </button>
        )
      })}
    </nav>
  )
}
