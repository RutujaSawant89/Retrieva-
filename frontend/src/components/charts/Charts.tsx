/* Chart building blocks shared by the dashboard, analytics and evaluation pages.
 *
 * Colors come from the validated --series-* tokens (fixed order, never cycled). Every chart
 * with two or more series has a legend, every chart has a hover tooltip, and every chart can
 * switch to a table view (the accessibility relief for low-contrast light-mode hues).
 */
import { BarChart3, Table2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { Button } from '@/components/ui/button'
import { Card, CardHeader, EmptyState, Skeleton } from '@/components/ui/primitives'
import { SERIES_COLORS } from '@/utils/chart'
import { cn } from '@/utils/cn'


export interface SeriesSpec {
  key: string
  label: string
}

type Row = Record<string, string | number | null | undefined>

export function StatTile({
  label,
  value,
  hint,
  icon,
  tone,
}: {
  label: ReactNode
  value: ReactNode
  hint?: ReactNode
  icon?: ReactNode
  tone?: 'default' | 'danger'
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <p className="text-[12.5px] font-medium text-muted-foreground">{label}</p>
        {icon && <span className="text-muted-foreground [&_svg]:size-4">{icon}</span>}
      </div>
      <p className={cn('mt-2 text-2xl font-semibold tabular-nums tracking-tight', tone === 'danger' && 'text-danger')}>
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </Card>
  )
}

function Legend({ series }: { series: SeriesSpec[] }) {
  if (series.length < 2) return null
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 px-5 pt-3 text-xs text-muted-foreground">
      {series.map((s, i) => (
        <li key={s.key} className="flex items-center gap-1.5">
          <span className="h-2 w-3 rounded-sm" style={{ background: SERIES_COLORS[i] }} aria-hidden />
          {s.label}
        </li>
      ))}
    </ul>
  )
}

function ChartTooltip({
  active,
  payload,
  label,
  format,
  series,
  labelFormat,
}: {
  labelFormat?: (v: string) => string
  active?: boolean
  payload?: { dataKey: string; value: number | null; color: string }[]
  label?: string
  format: (v: number | null | undefined) => string
  series: SeriesSpec[]
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-[var(--shadow-pop)]">
      <p className="mb-1 font-medium text-foreground">{label && labelFormat ? labelFormat(label) : label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="flex items-center gap-2 text-muted-foreground">
          <span className="size-2 rounded-full" style={{ background: entry.color }} aria-hidden />
          <span>{series.find((s) => s.key === entry.dataKey)?.label ?? entry.dataKey}</span>
          <span className="ml-auto pl-3 font-medium tabular-nums text-foreground">{format(entry.value)}</span>
        </p>
      ))}
    </div>
  )
}

function DataTable({ data, xKey, xLabel, series, format }: { data: Row[]; xKey: string; xLabel: string; series: SeriesSpec[]; format: (v: number | null | undefined) => string }) {
  return (
    <div className="max-h-72 overflow-auto px-5 pb-4">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-surface text-left text-muted-foreground">
          <tr>
            <th className="py-2 font-medium">{xLabel}</th>
            {series.map((s) => (
              <th key={s.key} className="py-2 text-right font-medium">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {data.map((row, i) => (
            <tr key={i}>
              <td className="py-1.5">{String(row[xKey])}</td>
              {series.map((s) => (
                <td key={s.key} className="py-1.5 text-right tabular-nums">
                  {format(row[s.key] as number | null)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface ChartCardProps {
  title: string
  description?: ReactNode
  data: Row[] | undefined
  xKey: string
  xLabel?: string
  series: SeriesSpec[]
  format?: (v: number | null | undefined) => string
  loading?: boolean
  emptyText?: string
  height?: number
  kind: 'line' | 'bar'
  xFormatter?: (v: string) => string
  stacked?: boolean
}

const defaultFormat = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 2 })

export function ChartCard({
  title,
  description,
  data,
  xKey,
  xLabel = 'Date',
  series,
  format = defaultFormat,
  loading,
  emptyText = 'No data for this period yet',
  height = 220,
  kind,
  xFormatter,
  stacked,
}: ChartCardProps) {
  const [table, setTable] = useState(false)
  const hasData = !!data?.some((row) => series.some((s) => typeof row[s.key] === 'number' && (row[s.key] as number) !== 0))
  const axis = { stroke: 'var(--chart-axis)', fontSize: 11, tickLine: false, axisLine: false }

  return (
    <Card>
      <CardHeader
        title={title}
        description={description}
        action={
          hasData && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setTable((t) => !t)}
              aria-label={table ? 'Show chart' : 'Show data table'}
              title={table ? 'Show chart' : 'Show data table'}
            >
              {table ? <BarChart3 /> : <Table2 />}
            </Button>
          )
        }
      />
      {loading ? (
        <div className="p-5">
          <div style={{ height }}>
            <Skeleton className="h-full w-full" />
          </div>
        </div>
      ) : !hasData || !data ? (
        <EmptyState className="py-10" title={emptyText} />
      ) : table ? (
        <DataTable data={data} xKey={xKey} xLabel={xLabel} series={series} format={format} />
      ) : (
        <>
          <Legend series={series} />
          <div className="px-2 pb-3 pt-2" style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
              {kind === 'line' ? (
                <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey={xKey} {...axis} tickFormatter={xFormatter} minTickGap={24} />
                  <YAxis {...axis} width={48} tickFormatter={(v: number) => format(v)} />
                  <RechartsTooltip
                    cursor={{ stroke: 'var(--chart-axis)', strokeDasharray: '3 3' }}
                    content={<ChartTooltip format={format} series={series} labelFormat={xFormatter} />}
                  />
                  {series.map((s, i) => (
                    <Line
                      key={s.key}
                      type="monotone"
                      dataKey={s.key}
                      stroke={SERIES_COLORS[i]}
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)' }}
                      connectNulls
                    />
                  ))}
                </LineChart>
              ) : (
                <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }} barGap={2}>
                  <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                  <XAxis dataKey={xKey} {...axis} tickFormatter={xFormatter} minTickGap={12} />
                  <YAxis {...axis} width={48} tickFormatter={(v: number) => format(v)} />
                  <RechartsTooltip
                    cursor={{ fill: 'var(--surface-2)' }}
                    content={<ChartTooltip format={format} series={series} labelFormat={xFormatter} />}
                  />
                  {series.map((s, i) => (
                    <Bar
                      key={s.key}
                      dataKey={s.key}
                      fill={SERIES_COLORS[i]}
                      radius={stacked ? 0 : [4, 4, 0, 0]}
                      maxBarSize={36}
                      stackId={stacked ? 'stack' : undefined}
                      stroke="var(--surface)"
                      strokeWidth={stacked ? 1 : 0}
                    />
                  ))}
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        </>
      )}
    </Card>
  )
}

