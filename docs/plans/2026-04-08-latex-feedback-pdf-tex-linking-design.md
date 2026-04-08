# 2026-04-08 LaTeX 点评修订与 PDF/TeX 双向高亮设计

## 1. 当前状态

已落地：
- `main.tex`（及其他文本文件）可直接划词点评。
- 点评可触发 AI 改写，支持两种范围：
  - 仅改写选区
  - 重写所在 section
- 点评列表可持久化（项目 `llm_config.metadata.feedback_items`）。

未落地：
- PDF 预览中的划词点评。
- PDF 高亮与 TeX 高亮双向联动。

---

## 2. 目标能力

用户在任一侧操作，另一侧同步高亮：

1. 在 TeX 中划词点评：
- TeX 选区高亮。
- PDF 中对应文字同步标黄。

2. 在 PDF 中划词点评：
- PDF 选区高亮。
- TeX 中对应文字同步标黄。

3. 点评项可稳定重定位：
- 文本改写后仍尽量找到原锚点（anchor）。

---

## 3. 架构方案（分层）

### 3.1 前端展示层

- 将当前 `iframe` PDF 预览升级为 PDF.js text-layer 方案（可选中真实文本 span）。
- 左侧 TeX 编辑器从 `textarea` 逐步升级到可装饰范围高亮的编辑器（CodeMirror 方案优先）。
- 定义统一高亮事件：
  - `feedback:focus(id)`
  - `feedback:hover(id)`
  - `feedback:create(source, range, anchor)`

### 3.2 映射层（核心）

采用“双轨映射”：

1. **结构映射（主）**：SyncTeX
- 编译阶段产出 `.synctex.gz`。
- 使用 `synctex view` / `synctex edit` 做 TeX↔PDF 坐标映射。

2. **文本映射（辅）**：锚点 + 模糊匹配
- 当 SyncTeX 不可用或精度不足时，使用：
  - `selected_text`
  - `prefix/suffix`
  - `heading_title/heading_level`
  - `line_hint`
 进行回退定位。

### 3.3 数据层

每条点评扩展为双锚点结构：

```json
{
  "id": "...",
  "source": "tex|pdf",
  "file_path": "main.tex",
  "start": 120,
  "end": 168,
  "selected_text": "...",
  "anchor": { "...": "tex anchor" },
  "pdf_anchor": {
    "history_id": "compile-history-id",
    "page": 3,
    "quad_points": [ ... ],
    "text": "..."
  },
  "mapping_confidence": 0.92
}
```

---

## 4. 后端接口设计

建议新增：

1. `POST /latex/projects/{id}/feedback/map`
- 输入：`tex range` 或 `pdf selection`
- 输出：双向映射结果（TeX range + PDF quads + confidence）

2. `GET /latex/projects/{id}/compile/{history_id}/synctex`
- 输出：当前编译产物对应 synctex 可用性信息

3. `POST /latex/projects/{id}/feedback/rewrite`
- 已有（本次已接入）
- 后续扩展返回 `pdf_anchor` 更新结果

---

## 5. 前端交互策略

### 5.1 创建点评

- `source=tex`：从编辑器选区创建，立即请求 map 得到 pdf anchor。
- `source=pdf`：从 PDF text-layer 选区创建，立即请求 map 得到 tex range。

### 5.2 高亮联动

- 选中点评卡片：
  - TeX 编辑器高亮对应 range。
  - PDF 页滚动到目标页并绘制透明黄底 overlay。

### 5.3 失败回退

- 映射失败时只高亮源侧，另一侧提示“未找到稳定映射”。
- 允许用户手动“重新绑定”。

---

## 6. 分阶段实施建议

### Phase A（已完成）
- TeX 划词点评 + AI 改写（selection/section）。

### Phase B
- PDF.js text-layer 替换 iframe。
- 支持 PDF 选区创建点评（先不联动 TeX）。

### Phase C
- 编译链路接入 SyncTeX 元数据。
- 后端 `map` API 打通 TeX↔PDF 双向映射。

### Phase D
- 双侧稳定高亮 + 改写后锚点更新 + 映射置信度回退策略。

---

## 7. 风险点

- 不同 TeX 宏包和复杂环境下，SyncTeX 坐标不稳定。
- PDF text-layer 与视觉字形不完全一致（连字、数学公式）。
- 大段重写后点评锚点漂移，需二次重定位与低置信告警。

---

## 8. 验收标准

- 在 `main.tex` 创建点评后，能触发改写并保持点评可定位。
- 在 PDF 端创建点评后，能映射出 TeX 范围（置信度可见）。
- 任意点评聚焦时，TeX 与 PDF 两侧均有可见高亮，且滚动定位正确。
