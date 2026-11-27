"use client";

import { useId, useState } from "react";

export function StudyTrend({
  hours: trendHours,
  reviews: trendReviews,
  days: labels,
  compact = false,
}: {
  hours: number[];
  reviews: number[];
  days: string[];
  compact?: boolean;
}) {
  const identifier = useId().replace(/:/g, "");
  const [selected, setSelected] = useState<number | null>(null);
  const x = (index: number) =>
    38 + index * (442 / Math.max(1, trendHours.length - 1));
  const maxHours = Math.max(6, Math.ceil(Math.max(...trendHours, 0) / 2) * 2);
  const maxReviews = Math.max(
    15,
    Math.ceil(Math.max(...trendReviews, 0) / 5) * 5,
  );
  const y = (hours: number) => 160 - (hours / maxHours) * 132;
  const points = trendHours
    .map((hours, index) => `${x(index)},${y(hours)}`)
    .join(" ");
  if (trendHours.length === 0)
    return <div className="ds-empty">暂无学习趋势数据</div>;
  return (
    <div className={`ds-study-chart ${compact ? "is-compact" : ""}`}>
      <div className="ds-chart-legend">
        <span>
          <i className="ds-dot blue" />
          学习时长（小时）
        </span>
        <span>
          <i className="ds-dot purple" />
          复习完成数（右轴）
        </span>
      </div>
      <svg
        viewBox="0 0 525 198"
        role="img"
        aria-label="近14天学习时长和复习次数示例趋势"
      >
        <defs>
          <linearGradient id={`bars-${identifier}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#b99bff" stopOpacity=".8" />
            <stop offset="100%" stopColor="#e4d8ff" stopOpacity=".55" />
          </linearGradient>
          <linearGradient id={`area-${identifier}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6490ff" stopOpacity=".12" />
            <stop offset="100%" stopColor="#6490ff" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((index) => (
          <g key={index}>
            <line
              x1="32"
              x2="492"
              y1={y((index / 3) * maxHours)}
              y2={y((index / 3) * maxHours)}
              stroke="#edf1f8"
              strokeDasharray="3 4"
            />
            <text
              x="5"
              y={y((index / 3) * maxHours) + 4}
              className="ds-svg-label"
            >
              {Math.round((index / 3) * maxHours)}h
            </text>
            <text
              x="501"
              y={y((index / 3) * maxHours) + 4}
              className="ds-svg-label"
            >
              {Math.round((index / 3) * maxReviews)}
            </text>
          </g>
        ))}
        <polygon
          points={`38,160 ${points} 480,160`}
          fill={`url(#area-${identifier})`}
        />
        {trendReviews.map((count, index) => (
          <rect
            key={index}
            x={x(index) - 6}
            y={160 - (count / maxReviews) * 132}
            width="12"
            height={(count / maxReviews) * 132}
            rx="2"
            fill={`url(#bars-${identifier})`}
          >
            <title>{`${labels[index]} · 完成复习 ${count} 次`}</title>
          </rect>
        ))}
        <polyline
          points={points}
          fill="none"
          stroke="#4d80ff"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        {trendHours.map((hours, index) => (
          <g
            key={index}
            onMouseEnter={() => setSelected(index)}
            onMouseLeave={() => setSelected(null)}
          >
            <circle cx={x(index)} cy={y(hours)} r="12" fill="transparent" />
            <circle
              cx={x(index)}
              cy={y(hours)}
              r={selected === index ? 5 : 3.8}
              fill="#fff"
              stroke="#4d80ff"
              strokeWidth="2"
            />
            <text
              x={x(index)}
              y="185"
              textAnchor="middle"
              className="ds-svg-label"
            >
              {labels[index]}
            </text>
            <title>{`${labels[index]} · 学习 ${hours} 小时 · 复习 ${trendReviews[index]} 次`}</title>
          </g>
        ))}
      </svg>
      <div className="ds-chart-readout" aria-live="polite">
        {selected === null
          ? "示例趋势 · 可悬停查看每日数据"
          : `${labels[selected]}　学习 ${trendHours[selected]} 小时　完成复习 ${trendReviews[selected]} 次`}
      </div>
    </div>
  );
}

export function Donut({
  segments,
  total = "1,248",
  caption = "知识点",
  small = false,
}: {
  segments: { name: string; value: number; color: string }[];
  total?: string;
  caption?: string;
  small?: boolean;
}) {
  const sum = segments.reduce((value, segment) => value + segment.value, 0);
  if (sum <= 0) return <div className="ds-empty">暂无分布数据</div>;
  let offset = 0;
  const stops = segments.map((segment) => {
    const start = offset;
    offset += (segment.value / sum) * 100;
    return `${segment.color} ${start}% ${offset}%`;
  });
  return (
    <div className={`ds-donut-group ${small ? "small" : ""}`}>
      <div
        className="ds-donut"
        style={{ background: `conic-gradient(${stops.join(",")})` }}
        role="img"
        aria-label={segments
          .map((segment) => `${segment.name} ${segment.value}%`)
          .join("，")}
      >
        <div>
          <strong>{total}</strong>
          <span>{caption}</span>
        </div>
      </div>
      <div className="ds-donut-legend">
        {segments.map((segment) => (
          <div key={segment.name}>
            <span>
              <i style={{ background: segment.color }} />
              {segment.name}
            </span>
            <strong>{segment.value}%</strong>
          </div>
        ))}
      </div>
    </div>
  );
}
