'use client';

/**
 * 统计可视化（FE-03 / FE-06）：纯 CSS 渲染，无图表库依赖。
 * 数据直接来自 GET /statistics/overview 的 retention_trend 与 heatmap，
 * 不补点、不插值、不生成示例值；空数组如实提示。
 */

import { formatPercent } from '@/lib/format';
import type { HeatmapPoint, TrendPoint } from '@/types/api';

export function TrendChart({ points }: { points: TrendPoint[] }) {
  if (points.length === 0) {
    return <div className="notice notice--info">该时间范围内接口未返回留存趋势数据。</div>;
  }

  // 柱高按本区间的最大值归一化，不假设 value 一定是 0..1；数值本身照实展示。
  const max = Math.max(...points.map((p) => p.value), 0);
  const safeMax = max > 0 ? max : 1;

  return (
    <div className="trend">
      <div className="trend__bars">
        {points.map((point) => {
          const height = Math.max(2, (point.value / safeMax) * 100);
          return (
            <div className="trend__col" key={point.date} title={`${point.date}：${point.value}`}>
              <span className="trend__value">{formatPercent(point.value)}</span>
              <div className="trend__track">
                <div className="trend__bar" style={{ height: `${height}%` }} />
              </div>
              <span className="trend__label">{point.date.slice(5)}</span>
            </div>
          );
        })}
      </div>
      <p className="muted text-xs">
        共 {points.length} 个数据点；柱高按本区间最大值（{max}）归一化，标签为接口原始 value 的百分比展示。
      </p>
    </div>
  );
}

export function HeatmapCalendar({ points }: { points: HeatmapPoint[] }) {
  if (points.length === 0) {
    return <div className="notice notice--info">该时间范围内接口未返回热力图数据。</div>;
  }

  const max = Math.max(...points.map((p) => p.count), 0);
  const level = (count: number): number => {
    if (count <= 0 || max <= 0) return 0;
    return Math.min(4, Math.max(1, Math.ceil((count / max) * 4)));
  };

  return (
    <div>
      <div className="heatmap">
        {points.map((point) => (
          <div
            key={point.date}
            className={`heatmap__cell heatmap__cell--${level(point.count)}`}
            title={`${point.date}：${point.count} 次`}
            aria-label={`${point.date}：${point.count} 次`}
          />
        ))}
      </div>
      <div className="heatmap__legend">
        <span>共 {points.length} 天</span>
        <span>单日最高 {max} 次</span>
        <span className="heatmap__scale">
          <i className="heatmap__cell heatmap__cell--0" />
          <i className="heatmap__cell heatmap__cell--1" />
          <i className="heatmap__cell heatmap__cell--2" />
          <i className="heatmap__cell heatmap__cell--3" />
          <i className="heatmap__cell heatmap__cell--4" />
          少 → 多
        </span>
      </div>
    </div>
  );
}
