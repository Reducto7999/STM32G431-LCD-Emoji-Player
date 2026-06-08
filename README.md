# 基于蓝桥杯嵌入式练习平台的STM32G431RBT6 LCD 表情包移植说明

（如果发现别的问题会继续修复更新）
本工程用于把 GIF 或图片序列转换成 STM32 LCD 可显示的彩色帧数组，并在 LCD 屏幕中央循环播放。该工程基于比赛时所提供嵌入式资源包`\BSP\LCD_Driver\MDK5_LCD_HAL`的驱动进行修改，仅对`stm32g431rbt6 蓝桥杯嵌入式练习平台`进行适配，可直接烧录；对于其他平台，需要自行进行代码的修改。

## 一、更换其他表情包

1. 将新的 GIF 或图片序列放入：

   ```text
   python_extract_frames/全部GIF图片帧
   ```

   建议先清空或移走旧图片，否则脚本会把该目录下所有支持的图片一起导出。

2. 运行帧提取脚本： 

   ```text
   python_extract_frames/extract_frames.py
   ```

3. 脚本会重新生成文件并覆盖原有路径：

   ```text
   code/gif_animation.c
   code/gif_animation.h
   ```

4. 在 Keil 中编译并下载程序。

   如果 `gif_animation.c` 和 `gif_animation.h` 已经加入过工程，通常不需要重新添加文件，只需要重新编译。

## 二、显示效果

- 图像不会被拉伸或扭曲。
- 任何尺寸处理都会保持原始长宽比例。
- 图像会显示在 LCD 中央。
- 图像没有覆盖到的 LCD 区域会显示为白色背景。
- 当前 LCD 分辨率按 `320x240` 处理。

## 三、不同尺寸图片的兼容规则

当前脚本和显示代码可以兼容不同尺寸的图片，规则如下。

如果图片宽度小于或等于 `320`，并且高度小于或等于 `240`：

- 图片宽度小于 `320`：水平居中显示，左右空白区域为白色。
- 图片高度小于 `240`：垂直居中显示，上下空白区域为白色。
- 图片正好 `320x240`：铺满屏幕显示，不留白边。
- 例如 `240x240` 图片：会在 `320x240` LCD 中水平居中，左右各留下约 `40` 像素白边。
- 提取数组时不会改变原有图片尺寸。

如果图片宽度或高度至少有一个超过 LCD 分辨率：

- 提取数组前会先等比例缩小图片。
- 缩小后保证宽度小于或等于 `320`，高度小于或等于 `240`。
- 缩小后宽度或高度至少有一个刚好贴合屏幕边界。
- 例如 `640x480` 会缩小为 `320x240`。
- 例如 `400x200` 会缩小为 `320x160`，然后在 LCD 中垂直居中显示。
- 例如 `200x400` 会缩小为 `120x240`，然后在 LCD 中水平居中显示。

如果一组动画帧的尺寸不同，也可以显示：

- 每一帧都会按照自己的宽高重新居中。
- 外部未覆盖区域会重新刷成白色，避免上一帧较大、下一帧较小时留下残影。

为了动画更稳定，仍然建议同一个表情包里的帧尽量保持相同尺寸。

## 四、控制播放速度

帧切换间隔在 `code/gif_animation.h` 中设置：

```c
#define GIF_FRAME_DELAY_MS 50
```

上面的 `50` 是示例值，数值单位是毫秒。

- `0` 表示不额外延时，播放速度主要取决于 LCD 刷屏耗时。
- 数值越小，动画越快。
- 数值越大，动画越慢。
- 例如 `100` 表示每帧停留约 100ms。

重新运行 `python_extract_frames/extract_frames.py` 时，脚本会尽量保留当前 `gif_animation.h` 里的 `GIF_FRAME_DELAY_MS` 设置。

## 五、注意事项

- 新表情包尺寸可以超过 LCD 分辨率，脚本会在提取数组前等比例缩小到 `320x240` 以内。
- 帧数越多、颜色越复杂，生成的 `gif_animation.c` 越大，可能导致 Flash 空间不足。
- 如果编译提示 Flash 不够，可以减少帧数，或者在 `python_extract_frames/extract_frames.py` 中降低颜色数量。
- 当前脚本会将图片颜色转换为 RGB565 格式，便于 LCD 显示。
- 透明像素会按白色背景处理。

## 六、Flash 空间不足的报错

如果 Keil 编译时出现类似下面的报错：

```text
Error: L6406E: No space in execution regions
Error: L6407E: Sections of aggregate size ... could not fit
```

这通常不是 Python 运行错误，也不是 C 语法错误，而是 STM32 的 Flash 空间放不下当前生成的表情包数组。

表情包帧数组主要保存在：

```text
code/gif_animation.c
```

这些数组属于 `const` 数据，会被链接到 Flash 中。如果帧数、尺寸或颜色数太大，就可能导致程序无法链接。

例如 `STM32G431RBT6` 的 Flash 大小约为 `128KB`。如果当前表情包是 `28` 帧、每帧 `240x240`、`MAX_COLORS = 16`，生成的图片数据可能已经接近：

```text
120KB
```

这时即使 `MAX_COLORS` 已经调到 `16`，剩余空间也不足以继续放下 `main.c`、`lcd.c`、HAL 库和启动文件，所以仍然会报 Flash 不够。

解决建议按优先级尝试：

1. 减少帧数，例如把 `28` 帧减少到 `14` 帧，或者隔帧保留。
2. 减小图片尺寸，例如从 `240x240` 降到 `200x200` 或更小。
3. 降低颜色数量，例如在 `python_extract_frames/extract_frames.py` 中设置：

   ```python
   MAX_COLORS = 8
   ```

4. 如果对颜色要求不高，可以把颜色量化方法改回更省空间的 `FASTOCTREE`：

   ```python
   method=Image.Quantize.FASTOCTREE
   ```

5. 在 Keil 中提高编译优化等级可以节省一部分代码空间，但核心占用通常仍然来自表情包帧数组。

每次修改图片、帧数、尺寸或 `MAX_COLORS` 后，都需要重新运行：

```text
python_extract_frames/extract_frames.py
```

然后重新编译工程。

## 七、镜像和颜色调试

如果 LCD 上显示出来的图片左右镜像，可以在 `code/gif_animation.h` 中调整：

```c
#define GIF_MIRROR_X_FIX  1
```

- `1`：修正左右镜像。
- `0`：不修正左右镜像。

如果 LCD 上显示出来的图片上下镜像，可以调整：

```c
#define GIF_MIRROR_Y_FIX  0
```

- `1`：修正上下镜像。
- `0`：不修正上下镜像。

重新运行 `python_extract_frames/extract_frames.py` 时，脚本会尽量保留当前 `gif_animation.h` 里的镜像修正设置。

如果颜色不是完全错误，而是部分颜色变得很不明显，通常不是数组提取错了，而是颜色压缩造成的：

- LCD 使用 RGB565，本身比电脑上的 24 位 RGB 少一些颜色层次。
- 为了节省 Flash，脚本会把每帧颜色压缩成有限数量的调色板颜色。
- 当前默认每帧最多使用 `64` 种颜色，比之前的 `16` 种颜色更接近原图。

颜色数量在 `python_extract_frames/extract_frames.py` 中设置：

```python
MAX_COLORS = 64
```

- 如果颜色仍然不明显，可以尝试改成 `128` 后重新运行脚本。
- 如果编译提示 Flash 不够，可以改回 `32` 或 `16`，但颜色细节会减少。

## 八、文件说明

- `python_extract_frames/extract_frames.py`：提取 GIF 或图片帧并生成 C 数组。
- `code/gif_animation.c`：保存生成的帧数据和 LCD 播放逻辑。
- `code/gif_animation.h`：保存帧尺寸、帧数、播放间隔等配置。
- `code/lcd.c`、`code/lcd.h`：LCD 底层显示接口。
