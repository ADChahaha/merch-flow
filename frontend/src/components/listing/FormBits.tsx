/** 上架表单共用的小组件与样式（B 站 / 淘宝两套表单都用）。 */

export const INPUT =
  'w-full rounded-md border border-slate-200 px-2.5 py-2 text-[12px] outline-none placeholder:text-slate-300 focus:border-brand-500'
export const CELL = 'w-full rounded border border-slate-200 px-1.5 py-1 text-[11px] outline-none focus:border-brand-500'

export function Section({
  index,
  title,
  hint,
  children,
}: {
  index: number
  title: string
  hint: string
  children: React.ReactNode
}) {
  return (
    <section className="mb-4 rounded-xl border border-slate-200 bg-white p-4">
      <header className="mb-3 flex items-baseline gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-600 text-[11px] font-medium text-white">
          {index}
        </span>
        <h2 className="text-[14px] font-semibold text-slate-800">{title}</h2>
        <span className="text-[11px] text-slate-400">{hint}</span>
      </header>
      {children}
    </section>
  )
}

export function Field({
  label,
  required,
  counter,
  children,
}: {
  label: string
  required?: boolean
  counter?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <label className="text-[12px] text-slate-600">
          {label}
          {required && <span className="ml-0.5 text-rose-500">*</span>}
        </label>
        {counter && <span className="text-[10px] text-slate-300 tabular-nums">{counter}</span>}
      </div>
      {children}
    </div>
  )
}
