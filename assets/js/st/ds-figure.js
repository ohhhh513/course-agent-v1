/**
 * 题库树/图 SVG 渲染（不依赖 ECharts）
 * DsFigure.mount(el, spec) / DsFigure.mountOptions(el, options_graph)
 */
(function (global) {
  var SVG_NS = "http://www.w3.org/2000/svg";

  function svgEl(name, attrs) {
    var el = document.createElementNS(SVG_NS, name);
    var k;
    if (attrs) {
      for (k in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, k) && attrs[k] != null) {
          el.setAttribute(k, String(attrs[k]));
        }
      }
    }
    return el;
  }

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function clear(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function uid(prefix) {
    return prefix + "-" + Math.random().toString(36).slice(2, 9);
  }

  function mountMatrix(host, spec) {
    var table = document.createElement("table");
    table.className = "ds-matrix";
    var nodes = spec.nodes || [];
    var matrix = spec.matrix || [];
    var thead = document.createElement("thead");
    var hr = document.createElement("tr");
    hr.appendChild(document.createElement("th"));
    nodes.forEach(function (name) {
      var th = document.createElement("th");
      th.textContent = name;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = document.createElement("tbody");
    matrix.forEach(function (row, i) {
      var tr = document.createElement("tr");
      var th = document.createElement("th");
      th.textContent = nodes[i] || i;
      tr.appendChild(th);
      (row || []).forEach(function (cell) {
        var td = document.createElement("td");
        td.textContent = cell;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    host.appendChild(table);
  }

  function layoutBinaryTree(spec) {
    var nodes = spec.nodes || [];
    var byId = {};
    nodes.forEach(function (id) {
      byId[id] = { id: id, left: null, right: null, x: 0, y: 0 };
    });
    (spec.edges || []).forEach(function (e) {
      if (!byId[e.from] || !byId[e.to]) return;
      if (e.position === "left") byId[e.from].left = byId[e.to];
      else byId[e.from].right = byId[e.to];
    });
    var root = byId[spec.root] || byId[nodes[0]];
    if (!root) return { nodes: [], edges: [], width: 120, height: 80 };

    // 左右子树分占互不重叠的水平区间，父结点取左右孩子中点；
    // 缺一侧时仍留空位，避免深浅子树把父结点拽到一边。
    var EMPTY = 1;
    function place(node, origin, depth) {
      node.y = depth;
      if (!node.left && !node.right) {
        node.x = origin;
        return 1;
      }
      if (node.left && node.right) {
        var wL = place(node.left, origin, depth + 1);
        var wR = place(node.right, origin + wL, depth + 1);
        node.x = (node.left.x + node.right.x) / 2;
        return wL + wR;
      }
      if (node.left) {
        var wLeft = place(node.left, origin, depth + 1);
        var fakeRight = origin + wLeft + EMPTY * 0.5;
        node.x = (node.left.x + fakeRight) / 2;
        return wLeft + EMPTY;
      }
      var wRight = place(node.right, origin + EMPTY, depth + 1);
      var fakeLeft = origin + EMPTY * 0.5;
      node.x = (fakeLeft + node.right.x) / 2;
      return EMPTY + wRight;
    }
    place(root, 0, 0);

    var minX = Infinity;
    var maxX = -Infinity;
    var maxY = 0;
    nodes.forEach(function (id) {
      var n = byId[id];
      if (n.x < minX) minX = n.x;
      if (n.x > maxX) maxX = n.x;
      if (n.y > maxY) maxY = n.y;
    });
    if (!isFinite(minX)) minX = 0;
    if (!isFinite(maxX)) maxX = 0;
    var gapX = 56;
    var gapY = 58;
    var pad = 32;
    var laid = [];
    nodes.forEach(function (id) {
      var n = byId[id];
      laid.push({
        id: id,
        x: pad + (n.x - minX) * gapX,
        y: pad + n.y * gapY
      });
    });
    var edges = [];
    (spec.edges || []).forEach(function (e) {
      var a = byId[e.from];
      var b = byId[e.to];
      if (!a || !b) return;
      edges.push({
        x1: pad + (a.x - minX) * gapX,
        y1: pad + a.y * gapY,
        x2: pad + (b.x - minX) * gapX,
        y2: pad + b.y * gapY
      });
    });
    return {
      nodes: laid,
      edges: edges,
      width: Math.max(140, pad * 2 + (maxX - minX) * gapX),
      height: pad * 2 + (maxY + 1) * gapY
    };
  }

  function edgeLabel(e) {
    if (e.activity != null && e.weight != null) return e.activity + "=" + e.weight;
    if (e.weight != null) return String(e.weight);
    return "";
  }

  function undirectedAdj(nodes, edges) {
    var g = {};
    nodes.forEach(function (id) { g[id] = []; });
    (edges || []).forEach(function (e) {
      if (!g[e.from] || !g[e.to]) return;
      if (g[e.from].indexOf(e.to) < 0) g[e.from].push(e.to);
      if (g[e.to].indexOf(e.from) < 0) g[e.to].push(e.from);
    });
    return g;
  }

  function hamiltonCycle(nodes, edges) {
    var n = nodes.length;
    if (n < 3) return nodes.slice();
    var g = undirectedAdj(nodes, edges);
    var found = null;
    function dfs(path, used) {
      if (found) return;
      if (path.length === n) {
        if ((g[path[n - 1]] || []).indexOf(path[0]) >= 0) found = path.slice();
        return;
      }
      var nbrs = g[path[path.length - 1]] || [];
      var i;
      for (i = 0; i < nbrs.length; i++) {
        var v = nbrs[i];
        if (used[v]) continue;
        used[v] = true;
        path.push(v);
        dfs(path, used);
        path.pop();
        used[v] = false;
        if (found) return;
      }
    }
    var s;
    for (s = 0; s < n && !found; s++) {
      var used = {};
      used[nodes[s]] = true;
      dfs([nodes[s]], used);
    }
    return found || nodes.slice();
  }

  function isAdjacentOnRing(order, a, b) {
    var i = order.indexOf(a);
    var j = order.indexOf(b);
    if (i < 0 || j < 0) return false;
    var d = Math.abs(i - j);
    return d === 1 || d === order.length - 1;
  }

  function drawNodesEdges(host, layout, opts) {
    opts = opts || {};
    var svg = svgEl("svg", {
      viewBox: "0 0 " + layout.width + " " + layout.height,
      width: String(layout.width),
      height: String(layout.height),
      overflow: "visible"
    });
    var markerId = uid("arr");
    if (opts.directed) {
      var defs = svgEl("defs");
      var marker = svgEl("marker", {
        id: markerId,
        viewBox: "0 0 10 10",
        refX: "10",
        refY: "5",
        markerWidth: "12",
        markerHeight: "10",
        orient: "auto",
        markerUnits: "userSpaceOnUse"
      });
      var tip = svgEl("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#222" });
      marker.appendChild(tip);
      defs.appendChild(marker);
      svg.appendChild(defs);
    }

    var r = opts.radius || 16;
    var cx = 0;
    var cy = 0;
    layout.nodes.forEach(function (n) {
      cx += n.x;
      cy += n.y;
    });
    if (layout.nodes.length) {
      cx /= layout.nodes.length;
      cy /= layout.nodes.length;
    }

    function along(e, t, dist) {
      var dx = e.x2 - e.x1;
      var dy = e.y2 - e.y1;
      var len = Math.sqrt(dx * dx + dy * dy) || 1;
      var px = -dy / len;
      var py = dx / len;
      var mx = e.x1 + dx * t;
      var my = e.y1 + dy * t;
      if (px * (mx - cx) + py * (my - cy) < 0) {
        px = -px;
        py = -py;
      }
      return { x: mx + px * dist, y: my + py * dist };
    }

    layout.edges.forEach(function (e) {
      var x1 = e.x1;
      var y1 = e.y1;
      var x2 = e.x2;
      var y2 = e.y2;
      if (opts.directed) {
        var dx = x2 - x1;
        var dy = y2 - y1;
        var len = Math.sqrt(dx * dx + dy * dy) || 1;
        var ux = dx / len;
        var uy = dy / len;
        x1 = e.x1 + ux * r;
        y1 = e.y1 + uy * r;
        x2 = e.x2 - ux * r;
        y2 = e.y2 - uy * r;
      }
      var lineAttrs = {
        x1: x1, y1: y1, x2: x2, y2: y2,
        stroke: "#333",
        "stroke-width": "1.5"
      };
      if (opts.directed) lineAttrs["marker-end"] = "url(#" + markerId + ")";
      svg.appendChild(svgEl("line", lineAttrs));
    });

    var labelPlaced = [];
    layout.edges.forEach(function (e, i) {
      if (!e.label) return;
      var dist = e.hull ? 14 : 11;
      var tList = e.hull
        ? [0.5, 0.4, 0.6, 0.35, 0.65]
        : (i % 2 ? [0.68, 0.32, 0.75, 0.25, 0.55] : [0.32, 0.68, 0.25, 0.75, 0.45]);
      var pos = along(e, tList[0], dist);
      var ti;
      for (ti = 0; ti < tList.length; ti++) {
        var p = along(e, tList[ti], dist);
        var clash = false;
        var k;
        for (k = 0; k < labelPlaced.length; k++) {
          var ddx = p.x - labelPlaced[k].x;
          var ddy = p.y - labelPlaced[k].y;
          if (ddx * ddx + ddy * ddy < 16 * 16) {
            clash = true;
            break;
          }
        }
        if (!clash) {
          pos = p;
          break;
        }
      }
      var tw = 7 * String(e.label).length + 8;
      var th = 15;
      svg.appendChild(svgEl("rect", {
        x: pos.x - tw / 2,
        y: pos.y - th + 4,
        width: tw,
        height: th,
        rx: 2,
        fill: "#fff"
      }));
      var lab = svgEl("text", {
        x: pos.x,
        y: pos.y,
        "text-anchor": "middle",
        "font-size": "11",
        fill: "#222"
      });
      lab.textContent = e.label;
      svg.appendChild(lab);
      labelPlaced.push(pos);
    });

    layout.nodes.forEach(function (n) {
      svg.appendChild(svgEl("circle", {
        cx: n.x, cy: n.y, r: r,
        fill: "#fff", stroke: "#333", "stroke-width": "1.5"
      }));
      var t = svgEl("text", {
        x: n.x, y: n.y + 4,
        "text-anchor": "middle",
        "font-size": n.id.length > 3 ? "10" : "12",
        fill: "#111"
      });
      t.textContent = n.id;
      svg.appendChild(t);
    });
    host.appendChild(svg);
  }

  function circleLayout(spec, directed) {
    var nodes = spec.nodes || [];
    var n = nodes.length || 1;
    var order = hamiltonCycle(nodes, spec.edges || []);
    var R = n <= 4 ? 86 : 124;
    var cx = R + 64;
    var cy = R + 64;
    var pos = {};
    order.forEach(function (id, i) {
      var a = -Math.PI / 2 + (2 * Math.PI * i) / n;
      pos[id] = { id: id, x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) };
    });
    var edges = (spec.edges || []).map(function (e) {
      var a = pos[e.from];
      var b = pos[e.to];
      if (!a || !b) return null;
      return {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        label: edgeLabel(e),
        hull: isAdjacentOnRing(order, e.from, e.to)
      };
    }).filter(Boolean);
    return {
      nodes: order.map(function (id) { return pos[id]; }),
      edges: edges,
      width: cx * 2,
      height: cy * 2,
      directed: directed
    };
  }

  function layerLayout(spec, directed) {
    var nodes = spec.nodes || [];
    var edges = spec.edges || [];
    var indeg = {};
    var adj = {};
    nodes.forEach(function (id) {
      indeg[id] = 0;
      adj[id] = [];
    });
    edges.forEach(function (e) {
      if (!adj[e.from]) adj[e.from] = [];
      adj[e.from].push(e.to);
      indeg[e.to] = (indeg[e.to] || 0) + 1;
      if (indeg[e.from] == null) indeg[e.from] = 0;
    });
    // BFS 最短层：源点的多个后继排在同一列，避免 1→2 与 1→3 共线
    var layer = {};
    var q = [];
    nodes.forEach(function (id) {
      if (!indeg[id]) {
        layer[id] = 0;
        q.push(id);
      }
    });
    var qi = 0;
    while (qi < q.length) {
      var u = q[qi++];
      (adj[u] || []).forEach(function (v) {
        if (layer[v] == null) {
          layer[v] = layer[u] + 1;
          q.push(v);
        }
      });
    }
    nodes.forEach(function (id) {
      if (layer[id] == null) layer[id] = 0;
    });
    var buckets = {};
    var maxL = 0;
    nodes.forEach(function (id) {
      var L = layer[id];
      if (!buckets[L]) buckets[L] = [];
      buckets[L].push(id);
      if (L > maxL) maxL = L;
    });
    Object.keys(buckets).forEach(function (k) {
      buckets[k].sort();
    });
    var gapX = 110;
    var gapY = 80;
    var pad = 32;
    var pos = {};
    var maxCol = 1;
    var L;
    for (L = 0; L <= maxL; L++) {
      var col = buckets[L] || [];
      if (col.length > maxCol) maxCol = col.length;
      col.forEach(function (id, i) {
        pos[id] = {
          id: id,
          x: pad + L * gapX,
          y: pad + i * gapY + ((maxCol - col.length) * gapY) / 2
        };
      });
    }
    var laidEdges = edges.map(function (e) {
      var a = pos[e.from];
      var b = pos[e.to];
      if (!a || !b) return null;
      return { x1: a.x, y1: a.y, x2: b.x, y2: b.y, label: edgeLabel(e) };
    }).filter(Boolean);
    return {
      nodes: nodes.map(function (id) { return pos[id]; }),
      edges: laidEdges,
      width: pad * 2 + maxL * gapX,
      height: pad * 2 + maxCol * gapY,
      directed: directed
    };
  }

  function isDirectedType(type) {
    type = String(type || "");
    if (type === "aoe_network") return true;
    if (type.indexOf("undirected") >= 0) return false;
    return type.indexOf("directed") >= 0;
  }

  function mountGraph(host, spec) {
    var type = spec.type || "";
    var directed = isDirectedType(type);
    var layout;
    if (type === "aoe_network") layout = layerLayout(spec, true);
    else layout = circleLayout(spec, directed);
    drawNodesEdges(host, layout, { directed: layout.directed, radius: 16 });
  }

  function mountTree(host, spec, compact) {
    var layout = layoutBinaryTree(spec);
    if (compact) {
      layout.width = Math.max(layout.width * 0.85, 120);
    }
    drawNodesEdges(host, layout, { directed: false, radius: compact ? 13 : 16 });
  }

  function mount(host, spec) {
    if (!host) return;
    clear(host);
    if (!spec || !spec.type) return;
    if (spec.type === "adjacency_matrix") {
      mountMatrix(host, spec);
      return;
    }
    if (spec.type === "tree") {
      mountTree(host, spec, false);
      return;
    }
    mountGraph(host, spec);
  }

  function mountOptions(host, map) {
    if (!host || !map) return;
    clear(host);
    ["A", "B", "C", "D"].forEach(function (key) {
      if (!map[key]) return;
      var box = document.createElement("div");
      box.className = "ds-option-fig";
      box.setAttribute("data-option", key);
      var cap = document.createElement("div");
      cap.textContent = key;
      box.appendChild(cap);
      var fig = document.createElement("div");
      mountTree(fig, map[key], true);
      box.appendChild(fig);
      host.appendChild(box);
    });
  }

  global.DsFigure = {
    mount: mount,
    mountOptions: mountOptions
  };
})(window);
