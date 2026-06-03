# Region-Focused Iterative Painting — 实现规格说明

> 本文档供 Copilot 辅助实现时参考。描述如何围绕 `forza-painter-geometrize-go.exe` 构建"分区域、分阶段"的迭代式几何化工作流，让用户将有限的图层预算精准分配到画面的重点区域。

---

## 1. 背景：exe 文件的行为

### 1.1 命令行接口

```
forza-painter-geometrize-go.exe <image.png> [flags]

Flags:
  -backend string     GPU backend: opencl (default) or vulkan
  -output string      Output JSON path prefix (default: derived from input path)
  -preview string     Optional preview PNG output path prefix
  -profile string     Profile name fragment under ./settings/
  -resume string      Resume from a saved geometry checkpoint JSON
  -seed int           Optional RNG seed for reproducible output
  -settings string    Path to settings INI file
```

### 1.2 关键机制

- **输入**：一张 PNG/JPEG 图片
- **过程**：迭代生成旋转椭圆（type 16），逐步逼近原图
- **输出**：JSON 文件（几何图形集合）+ 可选预览 PNG
- **resume**：通过 `-resume checkpoint.json` 从已有 JSON 恢复画布状态，然后继续生成新椭圆。resume 时引擎验证 `len(shapes) < stopAt`
- **透明保护**：图片 alpha 通道中透明（alpha≈0）的像素会被标记为 opaqueMask=0，不参与误差计算，也不会被椭圆覆盖

---

## 2. JSON 格式（exe 的输入/输出）

### 2.1 完整结构

```json
{
  "shapes": [
    {
      "type": 1,
      "data": [0, 0, 2000, 1500],
      "color": [128, 128, 128, 255],
      "score": 0.123456
    },
    {
      "type": 16,
      "data": [500.0, 300.0, 120.96, 80.64, 45.0],
      "color": [200, 100, 50, 200],
      "score": 0.015000
    }
  ]
}
```

### 2.2 Shape 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | int | 1=背景矩形, 16=旋转椭圆 |
| `data` | []float64 | 几何参数（见下表） |
| `color` | []int | RGBA，范围 0-255 |
| `score` | float64 | 该图形的误差分数（6 位小数精度） |

### 2.3 背景图形（type 1）

```json
{"type": 1, "data": [0, 0, width, height], "color": [r, g, b, a]}
```
- `data[0..3]` = `[左, 上, 宽度, 高度]`
- 永远是 shapes 数组的第一个元素
- resume 时引擎会自动跳过 type 1 图形（通过 `looksLikeBackground` 判断）

### 2.4 旋转椭圆（type 16）

```json
{"type": 16, "data": [x, y, rx, ry, theta], "color": [r, g, b, a]}
```
- `data[0]` = X：椭圆中心 X 坐标（整数，范围 `[0, width-1]`）
- `data[1]` = Y：椭圆中心 Y 坐标（整数，范围 `[0, height-1]`）
- `data[2]` = RX：水平半轴半径，**必须**是 `k × 0.63` 的倍数（k 为整数 ≥ 1）
- `data[3]` = RY：垂直半轴半径，同上量化为 k × 0.63
- `data[4]` = Theta：旋转角度（整数度数，范围 0-360）
- `color[0..3]` = RGBA（0-255 整数）

### 2.5 坐标系

- 所有坐标在**工作图像**的像素空间中（即经过 maxResolution 缩放后的图像）
- 原点为左上角，X 向右，Y 向下
- 像素索引：`idx = (y * width + x) * 4`

---

## 3. INI 设置文件格式

### 3.1 完整字段

```ini
description = Profile name
maxPreviewSize = 500           # 预览图最大尺寸
maxResolution = 1200           # 工作图像最大分辨率（缩放后）
maxThreads = 0                 # CPU 线程数（0=自动）
mutatedSamples = 3000          # 爬山算法的变异样本数
forceOpaqueShapes = false      # 强制所有图形 alpha=1
posterizeLevels = 20           # 颜色量化级别
previewEvery = 50              # 每 N 个图形保存一次预览
randomSamples = 50000          # 随机候选样本数
saveAt = 500,1000,1500,2000    # 逗号分隔：在这些图形数时保存 JSON checkpoint
saveEvery = 50                 # 每 N 个图形保存一次 JSON
stopAt = 3000                  # 目标图形总数（主循环终止条件）
useWorkGroupEval = true        # GPU workgroup 优化
enableProgressiveSampling = false
progressiveSamplingStart = 10
progressiveSamplingEnd = 1
progressiveSamplingTransition = 0.45
progressiveSamplingCurve = 3
errorGridSize = 64             # GPU 误差直方图网格分辨率
loadGeometry =                 # 从 JSON checkpoint 恢复（等价于 -resume）
```

### 3.2 分段生成时需要动态修改的字段

| 字段 | 修改规则 |
|---|---|
| `stopAt` | 第一次：设为用户指定的基础层数；后续：设为 `已用层数 + 本次新增层数` |
| `saveAt` | 过滤掉所有 > stopAt 的值；如果不需要 checkpoint 可设为空或只保留 stopAt 本身 |
| 其余字段 | **原样保留**，不做修改 |

---

## 4. 分段生成工作流

### 4.1 核心理念

```
总预算 2000 层
  ├─ 第一次：全图生成 1000 层基础 → base.json
  ├─ 第二次：选区域 A，resume + 加 300 层 → merged.json
  ├─ 第三次：选区域 B，resume + 加 400 层 → merged.json
  └─ 第四次：选区域 C，resume + 加 300 层 → final.json
```

### 4.2 流程细节

#### 第一次（first-pass）

1. 读取用户提供的原始 INI，记录 `total_budget = stopAt`
2. 生成临时 INI：`stopAt = first_layers`，其余不变
3. 调用 exe：`exe input.png -settings temp.ini -output work/base -preview work/preview`
4. 保存工作分辨率的 target 原图（用于后续生成 mask 和预览渲染）
5. 写入状态文件 `work/state.json`

#### 第 N 次（region-pass）

1. 加载 `state.json`，检查剩余预算
2. 用户在前端页面选择区域 → 前端生成选区 mask（和 target 同尺寸的灰度图）
3. `apply_selection_mask(target, mask, region_target.png)` — 选区外 alpha→0
4. 生成临时 INI：`stopAt = used_layers + region_layers`，`saveAt = stopAt`
5. 调用 exe：`exe region_target.png -resume base.json -settings temp.ini`
6. exe 输出的 JSON 直接就是合并后的完整结果，覆盖 `base.json`
7. 用 Pillow 重新渲染完整预览图（因为 exe 输出的预览基于带 mask 的 target，不能直接用）
8. 更新 `state.json`

### 4.3 关键原理：为什么 resume + mask 可行

- resume 时引擎先把 base.json 中**所有**椭圆 apply 到 GPU 画布上
- 然后在新 target 图上继续生成椭圆
- 新 target 图中选区外像素 alpha=0 → opaqueMask=0 → 不参与误差计算
- 误差采样自然集中在选区内的像素
- 选区外的已有椭圆在画布上存在，但 target 对应位置透明 → 不产生误差 → 不影响新椭圆的选择

---

## 5. Python 实现架构

### 5.1 文件结构（放在前端 Python 项目中）

```
region_painter/
  workflow.py          # 核心流程函数（被前端调用）
  state_manager.py     # 工作状态持久化
  ini_manager.py       # INI 读取/修改/写入
  image_processor.py   # apply_selection_mask
  preview_renderer.py  # 纯 CPU 椭圆渲染生成预览图
```

### 5.2 架构分层

```
┌─────────────────────────────────────────┐
│              前端页面                     │
│  选区工具（矩形/椭圆/画笔/羽化）           │
│  生成 selection_mask (PIL Image 'L')      │
└──────────────┬──────────────────────────┘
               │ selection_mask (同尺寸灰度图)
┌──────────────▼──────────────────────────┐
│             核心层（纯逻辑）               │
│  workflow.py         ← 流程编排           │
│  state_manager.py    ← 状态管理           │
│  ini_manager.py      ← INI 修改           │
│  image_processor.py  ← mask 应用到 target │
│  preview_renderer.py ← CPU 预览渲染       │
└──────────────────────────────────────────┘
```

### 5.3 依赖

```
Pillow >= 10.0    # 图像处理 + 椭圆渲染
```

### 5.4 组件规格

#### `state_manager.py`

```python
class StateManager:
    def load(work_dir: str) -> dict: ...
    def save() -> None: ...
    def add_pass(mask_path: str, layers: int, json_path: str) -> None: ...
    def remaining_budget() -> int: ...
    def total_budget() -> int: ...
    def used_layers() -> int: ...
```

持久化文件 `{work_dir}/state.json`：
```json
{
    "original_image": "/path/to/input.png",
    "original_ini": "/path/to/settings.ini",
    "total_budget": 2000,
    "used_layers": 800,
    "working_width": 1200,
    "working_height": 900,
    "max_resolution": 1200,
    "max_preview_size": 500,
    "base_json": "work/base.json",
    "target_path": "work/target.png",
    "preview_path": "work/preview.png",
    "passes": [
        {"mask": null, "layers": 500, "json": "work/base.json"},
        {"mask": "work/pass_2_mask.png", "layers": 300, "json": "work/merged.json"}
    ]
}
```

#### `ini_manager.py`

```python
def modify_ini(
    original_path: str,
    output_path: str,
    stop_at: int,
    save_at: list[int] | None = None
) -> None:
    """
    读取原始 INI，修改 stopAt 和 saveAt，其余字段原样写入临时文件。

    解析规则：
    - 跳过 # 和 ; 开头的注释行
    - 跳过空行
    - key = value 格式，trim 空格
    - 不存在的字段保持原样
    """
```

#### `image_processor.py`

```python
def apply_selection_mask(
    target_path: str,
    mask: Image.Image,           # 'L' 模式，255=选中 0=排除
    output_path: str,
    feather_radius: int = 0      # 羽化半径（高斯模糊）
) -> None:
    """
    1. 加载 target PNG（RGBA）
    2. 如果 feather_radius > 0，对 mask 做 GaussianBlur
    3. 将 mask 值乘到 target 的 alpha 通道：
       new_alpha = original_alpha * (mask_pixel / 255)
    4. 保存为 PNG
    """
```

#### `preview_renderer.py`

```python
def render_preview(
    target_path: str,             # 工作分辨率的原图
    shapes: list[dict],           # JSON 中的 shapes 数组
    output_path: str,
    max_preview_size: int = 500
) -> None:
    """
    纯 CPU 渲染预览图（不需要 GPU/exe）：

    1. 用 Pillow 加载 target 作为画布底色
    2. 跳过 shapes[0]（type 1 背景图形）
    3. 对每个 type 16 椭圆：
       a. 解析 data=[x, y, rx, ry, theta], color=[r, g, b, a]
       b. 遍历 bounding box (x±rx+1, y±ry+1)
       c. 对每个像素判断 (dx',dy') 是否在旋转椭圆内：
          xr = dx*cos(θ) + dy*sin(θ)
          yr = -dx*sin(θ) + dy*cos(θ)
          xr²/rx² + yr²/ry² ≤ 1.0
          （使用像素中心 (x+0.5, y+0.5) 计算 dx, dy）
       d. alpha 混合：dst = dst*(1-α) + color*α
       e. color 反量化：byte/255 → float [0,1]
    4. 缩放到 max_preview_size 后保存 PNG
    """
```

#### `workflow.py`

```python
from typing import Callable
from PIL import Image

ProgressCallback = Callable[[str], None]

def run_first_pass(
    image_path: str,
    settings_path: str,
    first_layers: int,
    output_dir: str,
    exe_path: str = "forza-painter-geometrize-go.exe",
    on_progress: ProgressCallback | None = None
) -> dict:
    """返回 {"ok": bool, "state": dict, "error": str}"""

def run_region_pass(
    output_dir: str,
    region_layers: int,
    selection_mask: Image.Image,  # 'L' 模式，和 working 图同尺寸
    exe_path: str = "forza-painter-geometrize-go.exe",
    on_progress: ProgressCallback | None = None
) -> dict:
    """返回 {"ok": bool, "new_total": int, "error": str}"""

def get_status(output_dir: str) -> dict:
    """返回 {"total_budget": int, "used_layers": int, "remaining": int, "passes": list}"""

def finalize(output_dir: str, dest_path: str) -> dict:
    """返回 {"ok": bool, "output": str, "error": str}"""
```

`run_region_pass` 内部调用 exe 的命令行：
```
forza-painter-geometrize-go.exe <region_target.png> -resume <base.json> -settings <temp.ini>
```

---

## 6. 前端选区工具

### 6.1 选区 mask 规格

- **格式**：PIL Image，`'L'` 模式（8-bit 灰度）
- **尺寸**：必须和 working 图（target_path）完全一致
- **值含义**：255 = 完全选中（参与误差计算），0 = 完全排除，中间值 = 软过渡

### 6.2 工具列表

| 工具 | 交互方式 | mask 生成方式 |
|---|---|---|
| 矩形 | 拖拽画框 | `ImageDraw.rectangle([x1,y1,x2,y2], fill=255)` |
| 椭圆 | 拖拽画椭圆 | `ImageDraw.ellipse([x1,y1,x2,y2], fill=255)` |
| 画笔 | 鼠标按住涂抹 | `ImageDraw.line(points, fill=255, width=brush_size)` |
| 多边形 | 点击顶点，闭合 | `ImageDraw.polygon(points, fill=255)` |
| 羽化 | 滑块 0~20px | `mask.filter(ImageFilter.GaussianBlur(radius))` |

### 6.3 组合使用

- 所有工具操作同一张 mask Canvas
- 切换工具不清空 mask（支持先椭圆圈脸，再画笔修边）
- 提供"清除"按钮重置 mask
- 可选：实时显示半透明红色叠加层，让用户直观看到选区范围

---

## 7. 椭圆渲染公式（preview_renderer 参考）

从 `internal/render/ellipse.go`：

```
输入：c = Candidate{X, Y, RX, RY, Theta, R, G, B, A}

θ = Theta × π / 180
cosT = cos(θ), sinT = sin(θ)
invRX2 = 1 / (RX × RX)
invRY2 = 1 / (RY × RY)

bounding box: [X-RX-1, X+RX+1] × [Y-RY-1, Y+RY+1]

对 bounding box 内每个像素 (px, py)：
  dx = (px + 0.5) - X
  dy = (py + 0.5) - Y
  xr = dx × cosT + dy × sinT
  yr = -dx × sinT + dy × cosT

  if xr × xr × invRX2 + yr × yr × invRY2 ≤ 1.0:
      dst[px,py] = dst[px,py] × (1 - A) + color × A
```

---

## 8. 注意事项

### 8.1 maxResolution 一致性

- 首次运行时从 INI 读取 `maxResolution`，存入 state.json
- 后续所有操作（target 图加载、mask 尺寸、INI 生成）强制使用此值
- 如果用户换了不同 maxResolution 的 INI，坐标系会错乱

### 8.2 stopAt 计算

- `new_stop = used_layers + region_layers`
- resume 时引擎验证 `len(shapes) < stopAt`，所以 new_stop 必须 > used_layers
- 如果剩余预算不足，截断 `region_layers = remaining`

### 8.3 预览图更新

每次 region-pass 后必须重新渲染完整预览图，因为 exe 输出的预览基于选区 mask 图（有大面积透明），不能直接给用户看。

### 8.4 选区 mask 预览

前端可在图片上叠加半透明红色层显示当前 mask，让用户直观了解哪些区域会被优化。

---

## 9. 不做的事

- **不修改 Go 源码**
- **不需要 json_merger**：resume 模式下 exe 直接输出合并后的 JSON
- **不需要坐标换算**：mask 方案保持图像尺寸不变，所有坐标天然一致
- **不处理非 PNG 的 mask 存储**：mask 统一保存为 PNG 灰度图
