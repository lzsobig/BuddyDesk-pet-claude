# Pet Sprite Plan — Hermes Pet (Mochi-style)

## 风格
Mochi-style 软萌手绘风。无硬轮廓(body 用柔和径向渐变外加 1px 半透明高光,模拟 Q 弹果冻质感)。所有 sprite 在 64x64 透明画布上绘制,通过 scale factor 2 缩放到 128x128 显示,以保留抗锯齿和细节。

## 色板(取自 `assets/pet_reference.png`,与 spec 一致)
- 主色 cream `#FFF8E7` / light yolk `#FEEBC8`
- 阴影 milk-tea `#EAD4B3`(body 下方/侧面暗部)
- 眼睛 dark caramel `#3D2B1F`
- 鼻子 / 红晕 coral pink `#FF9E7D`
- 高光 纯白 `#FFFFFF`(opacity 0.55)

参考图采样确认主色调与上述色板高度一致(主色聚集在 #FEEFC8~#F0E0C0 区间)。

## 5 状态设计(每状态 1-2 帧,主程序 12 FPS 切换)
- **idle** (2 帧): 半圆 body + 大圆睁眼 + 短尾。帧 1 baseline,帧 2 整体上移 1px(呼吸)。尾巴轻微左右摆 ±2°。
- **walk** (2 帧): body 水平挤压 — 帧 1 压扁 (scaleX 1.08, scaleY 0.94),帧 2 拉长 (scaleX 0.94, scaleY 1.06)。整体水平位移 ±3px,尾巴 ±15° 大幅摆。
- **happy** (2 帧): 眼睛眯成弯月 `^_^`(用 2 段贝塞尔),身体上弹 4px(帧 1 顶位,帧 2 落位),尾巴剧烈摆 ±25°。
- **sleep** (1 帧静态): 眼睛一条横线 `-`,body 压扁到 0.85 高度,旁边浮 2-3 个 z 字符(独立半透明图层,向上漂 8px 循环)。
- **love** (1 帧静态): 眼睛变 `♥`(用 path 画实心心形),body 周围 4-6 个小爱心 sprite 按 1s 周期向外发射并淡出。

## Sprite 布局(Python dict 形式)
```python
self.sprites = {
    "idle":  [frame_0, frame_1],      # 2 帧,呼吸
    "walk":  [frame_0, frame_1],      # 2 帧,挤压循环
    "happy": [frame_0, frame_1],      # 2 帧,弹跳
    "sleep": [frame_0],                # 1 帧 + z 字符动画
    "love":  [frame_0],                # 1 帧 + 爱心粒子
}
```
每帧是预渲染的 `QImage`(RGBA8888, 64x64)或 `QPixmap`。粒子(z 字符 / 红心)单独存 `self.particles[state]`,在主循环里 update。

## 建议技术路径
1. 用 `PIL.ImageDraw` + `PIL.ImageFilter` 在 256x256(2x 内部绘制,后 downsample 到 64x64)上离屏渲染每帧,得到柔和抗锯齿边缘。
2. 通过 `PIL.ImageQt.ImageQt(pil_image)` 转为 `QImage`,塞进 `QPixmap.fromImage`。
3. 主程序 `QTimer` 12 FPS 触发 `self.sprites[state][frame_idx % len]` 切换。
4. 不用逐帧手画 PNG(避免 50+ 文件膨胀),全部代码生成,部署时只缓存 5 个 PIL Image 对象。

## 文件落地
- `assets/pet_reference.png` — 已复制(1536x732 RGBA)
- sprite 帧**不**在本次任务中预生成(任务范围 = 资源 + 方案,不写代码)。代码生成 sprite 留给后续 coder agent。
