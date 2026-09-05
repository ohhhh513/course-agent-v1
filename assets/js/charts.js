/* ==========================================================================
   课程智能体系统 · 图表工厂（基于 ECharts 5）
   所有图表随主题自动重绘，颜色取自 CSS 变量
   ========================================================================== */
const Charts = (function () {

  const store = new Map();   // el -> { instance, builder }

  function cssVar(n) {
    return getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  }

  function tokens() {
    return {
      text: cssVar('--text'),
      text2: cssVar('--text-2'),
      dim: cssVar('--chart-axis'),
      split: cssVar('--chart-split'),
      surface: cssVar('--surface'),
      surface2: cssVar('--surface-2'),
      border: cssVar('--border'),
      brand: cssVar('--brand-500') || '#6366f1',
      accent: cssVar('--accent-500') || '#8b5cf6',
      ok: cssVar('--ok') || '#22c55e',
      warn: cssVar('--warn') || '#f59e0b',
      danger: cssVar('--danger') || '#ef4444',
      info: cssVar('--info') || '#38bdf8'
    };
  }

  function baseTooltip(t) {
    return {
      backgroundColor: t.surface,
      borderColor: t.border,
      borderWidth: 1,
      textStyle: { color: t.text, fontSize: 12 },
      extraCssText: 'box-shadow:0 8px 28px rgba(0,0,0,.3);border-radius:8px;padding:9px 12px;'
    };
  }

  /** 渲染并登记（主题切换后自动重绘） */
  function render(sel, builder) {
    const el = typeof sel === 'string' ? document.querySelector(sel) : sel;
    if (!el || !window.echarts) return null;
    let rec = store.get(el);
    if (rec && rec.instance) rec.instance.dispose();
    const inst = echarts.init(el, null, { renderer: 'canvas' });
    inst.setOption(builder(tokens()), true);
    store.set(el, { instance: inst, builder });
    // 修复 SPA view 切换后容器宽度未及时同步：等布局稳定后强制 resize（双重保险）
    requestAnimationFrame(() => inst && inst.resize());
    setTimeout(() => inst && inst.resize(), 60);
    return inst;
  }

  function resizeAll() { store.forEach(r => r.instance && r.instance.resize()); }
  function redrawAll() {
    store.forEach((r, el) => {
      if (!document.body.contains(el)) return;
      r.instance.dispose();
      const inst = echarts.init(el, null, { renderer: 'canvas' });
      inst.setOption(r.builder(tokens()), true);
      store.set(el, { instance: inst, builder: r.builder });
    });
  }
  window.addEventListener('resize', resizeAll);
  window.addEventListener('themechange', () => setTimeout(redrawAll, 60));

  /* ================= 1. 三大图谱（力导向关系图） ================= */
  function graph(sel, data, onClick) {
    const inst = render(sel, (t) => {
      const catColors = data.categories.map(c => c.color);
      const isKnowledge = data.graphType === 'knowledge';
      const relColor = { pre: t.brand, advance: t.accent, parallel: t.dim, split: t.accent, map: t.info, error: t.danger, support: t.info };
      const relName = { pre: '前置', advance: '进阶', parallel: '并列', split: '拆解', map: '映射', error: '错题', support: '支撑' };

      return {
        tooltip: Object.assign(baseTooltip(t), {
          formatter(p) {
            if (p.dataType === 'edge') {
              return `<b>${relName[p.data.relation] || '关联'}关系</b><br/>${p.data.source} → ${p.data.target}`;
            }
            const d = p.data;
            let html = `<b style="font-size:13px">${d.name}</b>`;
            if (d.mastery !== undefined) {
              html += `<br/>学习完成率：<b style="color:${d.itemStyle.color}">${d.mastery}%</b>`;
              html += `<br/>难度：${'★'.repeat(d.difficulty || 0)}`;
              html += `<br/>学时：${d.hours || 0} 学时`;
              if (d.isKey) html += `<br/><span style="color:${t.warn}">◆ 重难点</span>`;
            }
            if (d.achieve !== undefined) html += `<br/>达成度：<b>${d.achieve}%</b><br/>权重：${d.weight}%`;
            if (d.errorRate !== undefined) html += `<br/>错误率：<b style="color:${t.danger}">${d.errorRate}%</b><br/>关联知识点：${d.relatedKp} 个`;
            if (d.count !== undefined) html += `<br/>累计错题：<b>${d.count}</b> 人次`;
            return html + `<br/><span style="color:${t.dim};font-size:11px">点击查看详情</span>`;
          }
        }),
        legend: [{
          data: data.categories.map(c => c.name),
          textStyle: { color: t.text2, fontSize: 11.5 },
          top: 10, left: 14, itemWidth: 11, itemHeight: 11, itemGap: 12,
          icon: 'circle'
        }],
        animationDuration: 900,
        animationEasingUpdate: 'quinticInOut',
        series: [{
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          zoom: isKnowledge ? 0.92 : 1,
          categories: data.categories.map(c => ({ name: c.name, itemStyle: { color: c.color } })),
          force: {
            repulsion: isKnowledge ? 340 : 420,
            edgeLength: isKnowledge ? [70, 150] : [90, 180],
            gravity: 0.09,
            friction: 0.14
          },
          label: {
            show: true, position: 'right', color: t.text, fontSize: 11.5,
            formatter: (p) => p.data.name.length > 9 ? p.data.name.slice(0, 9) + '…' : p.data.name
          },
          emphasis: {
            focus: 'adjacency',
            scale: 1.12,
            label: { fontSize: 12.5, fontWeight: 'bold' },
            lineStyle: { width: 3 }
          },
          edgeSymbol: ['none', 'arrow'],
          edgeSymbolSize: 7,
          data: data.nodes.map(n => {
            const color = data.categories[n.category].color;
            const val = n.mastery !== undefined ? n.mastery : (n.achieve !== undefined ? n.achieve : 60);
            return Object.assign({}, n, {
              value: val,
              symbolSize: n.category === 0 && !isKnowledge ? 46 : (n.isKey ? 34 : 26),
              category: n.category,
              itemStyle: {
                color,
                borderColor: n.isKey ? t.warn : 'transparent',
                borderWidth: n.isKey ? 2 : 0,
                shadowBlur: 12, shadowColor: color + '55'
              }
            });
          }),
          links: data.links.map(l => ({
            source: l.source, target: l.target, relation: l.relation,
            lineStyle: {
              color: relColor[l.relation] || t.dim,
              width: l.relation === 'pre' ? 1.8 : 1.2,
              curveness: 0.14,
              opacity: 0.62,
              type: l.relation === 'parallel' ? 'dashed' : 'solid'
            }
          }))
        }]
      };
    });
    if (inst && onClick) {
      inst.on('click', (p) => { if (p.dataType === 'node') onClick(p.data); });
    }
    return inst;
  }

  /* ================= 2. 能力雷达图 ================= */
  function radar(sel, data) {
    return render(sel, (t) => ({
      tooltip: baseTooltip(t),
      legend: { bottom: 0, textStyle: { color: t.text2, fontSize: 11.5 }, itemWidth: 12, itemHeight: 8, itemGap: 16 },
      radar: {
        indicator: data.indicators,
        center: ['50%', '46%'], radius: '62%',
        axisName: { color: t.text2, fontSize: 11.5 },
        splitLine: { lineStyle: { color: t.split } },
        splitArea: { areaStyle: { color: ['transparent', 'rgba(99,102,241,.035)'] } },
        axisLine: { lineStyle: { color: t.split } }
      },
      series: [{
        type: 'radar', symbolSize: 4,
        data: data.series.map((s, i) => {
          const colors = [t.brand, t.dim, t.warn];
          return {
            name: s.name, value: s.data,
            lineStyle: { width: i === 0 ? 2.4 : 1.6, color: colors[i], type: i === 2 ? 'dashed' : 'solid' },
            itemStyle: { color: colors[i] },
            areaStyle: i === 0 ? { color: colors[i] + '33' } : (i === 1 ? { color: colors[i] + '18' } : undefined)
          };
        })
      }]
    }));
  }

  /* ================= 3. 成长轨迹 / 趋势折线 ================= */
  function line(sel, data, opts) {
    const o = opts || {};
    return render(sel, (t) => ({
      tooltip: Object.assign(baseTooltip(t), { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.split } } }),
      legend: { top: 0, right: 0, textStyle: { color: t.text2, fontSize: 11.5 }, itemWidth: 14, itemHeight: 8 },
      grid: { left: 4, right: 8, top: 36, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category', data: data.xAxis, boundaryGap: false,
        axisLine: { lineStyle: { color: t.split } },
        axisTick: { show: false },
        axisLabel: { color: t.dim, fontSize: 11 }
      },
      yAxis: {
        type: 'value', min: o.min !== undefined ? o.min : 0, max: o.max,
        axisLine: { show: false }, axisTick: { show: false },
        splitLine: { lineStyle: { color: t.split, type: 'dashed' } },
        axisLabel: { color: t.dim, fontSize: 11, formatter: o.fmt || '{value}' }
      },
      series: data.series.map(s => ({
        name: s.name, type: 'line', data: s.data, smooth: true,
        symbol: 'circle', symbolSize: 6,
        lineStyle: { width: 2.4, color: s.color, type: s.dashed ? 'dashed' : 'solid' },
        itemStyle: { color: s.color, borderWidth: 2, borderColor: t.surface },
        areaStyle: o.area ? {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: s.color + '3a' }, { offset: 1, color: s.color + '00' }]
          }
        } : undefined,
        markLine: (data.milestones && s === data.series[0]) ? {
          symbol: 'none', silent: true,
          lineStyle: { color: t.warn, type: 'dashed', width: 1 },
          label: { color: t.warn, fontSize: 10.5, formatter: p => p.name },
          data: data.milestones.map(m => ({ xAxis: m.x, name: m.label }))
        } : undefined
      }))
    }));
  }

  /* ================= 4. 柱状图（错误类型分布 / 时间分布） ================= */
  function bar(sel, data, opts) {
    const o = opts || {};
    return render(sel, (t) => {
      const palette = [t.danger, '#f97316', t.warn, '#a3e635', t.ok, t.info];
      return {
        tooltip: Object.assign(baseTooltip(t), { trigger: 'axis', axisPointer: { type: 'shadow' } }),
        grid: { left: 4, right: o.horizontal ? 40 : 8, top: 18, bottom: 4, containLabel: true },
        xAxis: o.horizontal
          ? { type: 'value', axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.split, type: 'dashed' } }, axisLabel: { color: t.dim, fontSize: 11 } }
          : { type: 'category', data: data.map(d => d.name), axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false }, axisLabel: { color: t.dim, fontSize: 11, interval: 0, rotate: o.rotate || 0 } },
        yAxis: o.horizontal
          ? { type: 'category', data: data.map(d => d.name), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.text2, fontSize: 11.5 } }
          : { type: 'value', axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: t.split, type: 'dashed' } }, axisLabel: { color: t.dim, fontSize: 11 } },
        series: [{
          type: 'bar',
          barMaxWidth: o.horizontal ? 16 : 26,
          data: data.map((d, i) => ({
            value: d.value,
            itemStyle: {
              color: o.color || palette[i % palette.length],
              borderRadius: o.horizontal ? [0, 5, 5, 0] : [5, 5, 0, 0]
            }
          })),
          label: o.showLabel ? {
            show: true, position: o.horizontal ? 'right' : 'top',
            color: t.text2, fontSize: 11, fontFamily: 'monospace',
            formatter: o.labelFmt || '{c}'
          } : undefined
        }]
      };
    });
  }

  /* ================= 5. 热力图（知识点 × 学生） ================= */
  function heatmap(sel, data, onClick) {
    // 后端返回: data.data[row][col] = score 二维矩阵, data.startedMask[row][col] = bool
    // ECharts heatmap 期望: [[colIdx, rowIdx, value], ...] 三元组格式
    const rawMatrix = data.data || [];
    const mask = data.startedMask || [];
    const flatData = [];
    for (let row = 0; row < rawMatrix.length; row++) {
      for (let col = 0; col < (rawMatrix[row] || []).length; col++) {
        const started = mask[row] ? mask[row][col] : true;
        const val = rawMatrix[row][col];
        if (started) {
          flatData.push([col, row, val]);
        } else {
          // 未学习的格子：value = null → ECharts 渲染为灰色
          flatData.push([col, row, null]);
        }
      }
    }

    const label = data.label || '学习完成率';
    const inst = render(sel, (t) => ({
      tooltip: Object.assign(baseTooltip(t), {
        position: 'top',
        formatter(p) {
          if (p.value[2] == null) {
            return `<b>${data.studentAxis[p.value[1]] || p.value[1]}</b><br/>${data.kpAxis[p.value[0]] || p.value[0]}<br/><span style="color:var(--text-2)">未开始学习</span>`;
          }
          return `<b>${(data.studentAxis[p.value[1]] || {}).name || data.studentAxis[p.value[1]] || p.value[1]}</b><br/>${data.kpAxis[p.value[0]] || p.value[0]}<br/>${label}：<b style="font-size:14px">${p.value[2]}%</b>`;
        }
      }),
      grid: { left: 4, right: 14, top: 56, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category', data: data.kpAxis, position: 'top',
        splitArea: { show: true, areaStyle: { color: ['transparent'] } },
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: t.text2, fontSize: 10.5, rotate: 38, interval: 0 }
      },
      yAxis: {
        type: 'category',
        data: (data.studentAxis || []).map(s => typeof s === 'object' ? s.name : s),
        splitArea: { show: true, areaStyle: { color: ['transparent'] } },
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: t.text2, fontSize: 11.5 }
      },
      visualMap: {
        min: 0, max: 100, calculable: true, orient: 'horizontal',
        right: 14, top: 8, itemWidth: 12, itemHeight: 92,
        textStyle: { color: t.dim, fontSize: 10.5 },
        inRange: { color: ['#ef4444', '#f97316', '#f59e0b', '#a3e635', '#22c55e'] }
      },
      series: [{
        type: 'heatmap', data: flatData,
        label: {
          show: true, color: '#0b1220', fontSize: 9.5, fontWeight: 600,
          formatter: p => p.value[2] == null ? '' : p.value[2]
        },
        itemStyle: { borderRadius: 3, borderColor: t.surface, borderWidth: 2 },
        emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,.4)', borderColor: t.brand, borderWidth: 2 } },
        progressive: 400
      }]
    }));
    if (inst && onClick) inst.on('click', p => onClick(p.value, data));
    return inst;
  }

  /* ================= 6. 环形占比图（预警构成等） ================= */
  function donut(sel, data, opts) {
    const o = opts || {};
    return render(sel, (t) => ({
      tooltip: Object.assign(baseTooltip(t), { trigger: 'item', formatter: '{b}<br/>{c} 人 ({d}%)' }),
      legend: {
        orient: 'vertical', right: 0, top: 'center',
        textStyle: { color: t.text2, fontSize: 11.5 }, itemWidth: 10, itemHeight: 10, itemGap: 10
      },
      series: [{
        type: 'pie', radius: ['52%', '76%'], center: ['34%', '50%'],
        avoidLabelOverlap: false, padAngle: 2,
        itemStyle: { borderRadius: 5, borderColor: t.surface, borderWidth: 2 },
        label: {
          show: true, position: 'center',
          formatter: () => `{a|${o.centerValue || ''}}\n{b|${o.centerLabel || ''}}`,
          rich: {
            a: { color: t.text, fontSize: 24, fontWeight: 'bold', fontFamily: 'monospace', lineHeight: 30 },
            b: { color: t.dim, fontSize: 11.5, lineHeight: 18 }
          }
        },
        emphasis: { label: { show: true }, scale: true, scaleSize: 6 },
        labelLine: { show: false },
        data: data.map(d => ({ name: d.name, value: d.value, itemStyle: { color: d.color } }))
      }]
    }));
  }

  /* ================= 7. 仪表盘（班级达标率） ================= */
  function gauge(sel, value, opts) {
    const o = opts || {};
    return render(sel, (t) => ({
      series: [{
        type: 'gauge', startAngle: 200, endAngle: -20, min: 0, max: 100,
        center: ['50%', '62%'], radius: '96%',
        progress: { show: true, width: 14, roundCap: true, itemStyle: { color: o.color || t.brand } },
        axisLine: { lineStyle: { width: 14, color: [[1, t.split]] } },
        pointer: { show: false },
        axisTick: { show: false }, splitLine: { show: false },
        axisLabel: { show: false },
        anchor: { show: false },
        title: { show: true, offsetCenter: [0, '24%'], color: t.dim, fontSize: 11.5 },
        detail: {
          valueAnimation: true, offsetCenter: [0, '-6%'],
          fontSize: 27, fontWeight: 'bold', fontFamily: 'monospace',
          color: t.text, formatter: '{value}%'
        },
        data: [{ value, name: o.name || '' }]
      }]
    }));
  }

  /* ================= 8. 分组柱状（班级对比） ================= */
  function groupBar(sel, data) {
    return render(sel, (t) => ({
      tooltip: Object.assign(baseTooltip(t), { trigger: 'axis' }),
      legend: { top: 0, textStyle: { color: t.text2, fontSize: 11.5 }, itemWidth: 12, itemHeight: 8 },
      grid: { left: 4, right: 8, top: 34, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category', data: data.categories,
        axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false },
        axisLabel: { color: t.dim, fontSize: 10.5, interval: 0, rotate: 18 }
      },
      yAxis: {
        type: 'value', axisLine: { show: false }, axisTick: { show: false },
        splitLine: { lineStyle: { color: t.split, type: 'dashed' } },
        axisLabel: { color: t.dim, fontSize: 11 }
      },
      series: data.series.map(s => ({
        name: s.name, type: 'bar', data: s.data, barMaxWidth: 18,
        itemStyle: { color: s.color, borderRadius: [4, 4, 0, 0] }
      }))
    }));
  }

  return { render, graph, radar, line, bar, heatmap, donut, gauge, groupBar, resizeAll, redrawAll, tokens };
})();
