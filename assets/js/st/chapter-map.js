/**
 * 王道小节 → 课程 9 章（课件视频清单）
 * 供题库页与后续接入 student 端复用。
 */
(function (global) {
  var CHAPTERS = [
    { id: 1, title: "第1章 绪论", prefixes: ["1."] },
    { id: 2, title: "第2章 线性表", prefixes: ["2."] },
    { id: 3, title: "第3章 栈和队列", prefixes: ["3.1", "3.2", "3.3"] },
    { id: 4, title: "第4章 串", prefixes: ["4."] },
    { id: 5, title: "第5章 数组和广义表", prefixes: ["3.4"] },
    { id: 6, title: "第6章 树和二叉树", prefixes: ["5."] },
    { id: 7, title: "第7章 图", prefixes: ["6."] },
    { id: 8, title: "第8章 查找", prefixes: ["7."] },
    { id: 9, title: "第9章 排序", prefixes: ["8."] }
  ];

  var UNCATEGORIZED = { id: 0, title: "未分类" };

  function mapSection(section) {
    var text = String(section || "");
    var i, ch, j;
    // 3.4 必须先于 3.1/3.2/3.3 之外的宽匹配；当前第3章不用 "3." 前缀
    for (i = 0; i < CHAPTERS.length; i++) {
      ch = CHAPTERS[i];
      for (j = 0; j < ch.prefixes.length; j++) {
        if (text.indexOf(ch.prefixes[j]) === 0) return ch;
      }
    }
    return UNCATEGORIZED;
  }

  function figureMode(q) {
    if (q && q.options_graph) return "option-figures";
    if (q && q.graph && q.graph.type === "adjacency_matrix") return "matrix";
    if (q && q.graph) return "stem-figure";
    return "text";
  }

  function normalize(q) {
    var course = mapSection(q.chapter);
    return {
      id: q.id,
      section: q.chapter,
      courseId: course.id,
      courseTitle: course.title,
      question: q.question || "",
      options: q.options || {},
      answer: q.answer,
      analysis: q.analysis || "",
      has_image: !!q.has_image,
      graph: q.graph || null,
      options_graph: q.options_graph || null,
      figureMode: figureMode(q)
    };
  }

  global.ChapterMap = {
    CHAPTERS: CHAPTERS,
    mapSection: mapSection,
    figureMode: figureMode,
    normalize: normalize
  };
})(window);
