/* ==========================================================================
   Course Agent · UI enhancements
   Adds action feedback and restrained data motion without changing view logic.
   ========================================================================== */
(function () {
  'use strict';

  const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const countSelector = '.stat__value, .cal-stat__num, .hero__ring b, .kp-stat b';

  function makeRipple(event) {
    if (reducedMotion) return;
    const host = event.target.closest('.btn, .nav-item, .seg button, .chip');
    if (!host || host.closest('.toast')) return;
    const rect = host.getBoundingClientRect();
    const ripple = document.createElement('span');
    ripple.className = 'ui-ripple';
    ripple.style.left = (event.clientX - rect.left) + 'px';
    ripple.style.top = (event.clientY - rect.top) + 'px';
    host.classList.add('ui-ripple-host');
    host.appendChild(ripple);
    // 收尾：摘掉涟漪，并在宿主内没有其它涟漪时移除宿主标记。
    // 必须幂等 —— animationend 与下面的兜底定时器都可能触发。
    const drop = () => {
      ripple.remove();
      if (!host.querySelector('.ui-ripple')) host.classList.remove('ui-ripple-host');
    };
    ripple.addEventListener('animationend', drop, { once: true });
    // 兜底：动画被中断 / animationend 丢失（后台标签页、被打断的动画）时，
    // 涟漪会永久留在宿主内。它带 margin:-6px，会持续挤压按钮宽度，
    // 所以无论动画事件是否到达，800ms 后都强制回收。
    setTimeout(drop, 800);
  }

  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function animateNumber(el) {
    if (reducedMotion || el.dataset.uiCounted || el.children.length) return;
    const raw = (el.textContent || '').trim();
    const match = raw.match(/^(-?\d[\d,]*(?:\.\d+)?)(.*)$/);
    if (!match) return;

    const target = Number(match[1].replace(/,/g, ''));
    if (!Number.isFinite(target) || Math.abs(target) > 1000000) return;
    const decimals = (match[1].split('.')[1] || '').length;
    const suffix = match[2] || '';
    const duration = 620;
    const start = performance.now();
    el.dataset.uiCounted = '1';

    function paint(now) {
      const progress = Math.min(1, (now - start) / duration);
      const value = target * easeOutCubic(progress);
      el.textContent = value.toFixed(decimals) + suffix;
      if (progress < 1) requestAnimationFrame(paint);
      else el.textContent = target.toFixed(decimals) + suffix;
    }
    requestAnimationFrame(paint);
  }

  function enhanceScope(scope) {
    const root = scope || document;
    root.querySelectorAll(countSelector).forEach(animateNumber);
  }

  function pinActiveNavigation() {
    const active = document.querySelector('.nav-item.is-active');
    if (active && window.innerWidth <= 760) {
      active.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'nearest', inline: 'center' });
    }
  }

  document.addEventListener('pointerdown', makeRipple, { passive: true });

  document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.add('ui-ready');
    enhanceScope(document);
    pinActiveNavigation();

    const content = document.querySelector('.content');
    if (!content || typeof MutationObserver === 'undefined') return;

    let timer = null;
    const observer = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        enhanceScope(content);
        pinActiveNavigation();
      }, 90);
    });
    observer.observe(content, { childList: true, subtree: true });
    window.addEventListener('hashchange', () => setTimeout(pinActiveNavigation, 40));
  });
})();
