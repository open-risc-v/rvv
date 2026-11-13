# W2 交叉编译基线（6 项：5 绿 + 1 待解）

范围：`data/waves.csv` 的 W2（6 项 / 515 人日）。目标是**每项先有"交叉编译能跑通、且与 native 输出一致"的基线**，
RVV 内核代码一行还没写——这与 W1 的口径完全一样：G2 只证明"同一份上游源码在 riscv64 上行为不变"。

## 1. 结果总表

| 包 | 工程 | 构建系统与关键开关 | 探针 | riscv64 与 native |
|---|---|---|---|---|
| media-libs/opus | `opus-rvv` | autotools，`OPUS_FIXED_POINT=ON` + `--disable-intrinsics` | 48 kHz/20 ms ×120 帧 CBR 64k | **全字段一致** |
| media-libs/libwebp | `libwebp-rvv` | CMake，静态 `webp`+`sharpyuv` | 133×101 无损回环 + q=75 有损 | **全字段一致**（`px_diff=0`） |
| media-libs/libvpx | `libvpx-rvv` | configure `--target=generic-gnu`（**无 riscv 目标**） | VP8 128×96 ×10 帧 CBR、cpu-used=0 | **全字段一致** |
| media-libs/openh264 | `openh264-rvv` | Makefile，`USE_ASM=No` | H.264 128×96 ×10 帧，逐 NAL 解码 | **全字段一致** |
| media-libs/libaom | `libaom-rvv` | CMake，`AOM_TARGET_CPU=generic` | AV1 128×96 ×5 帧 AOM_Q、cpu-used=8 | **全字段一致** |
| media-libs/webrtc-audio-processing | `webrtc-ap-rvv` | meson + abseil 20240722.0 wrap | APM 48 kHz/10 ms ×200 帧 | **未跑通**（见 §4） |

实测输出（可直接作为后续回归的期望值）：

```
opus      frames=120 bytes=19200 fnv_bit=a04caa33e5671901 pcm=115200 fnv_pcm=74bc2325f58a2e04 ver=libopus unknown-fixed
libwebp   size=133x101 lossless=30026 fnv_ll=69c27e48073e9609 px_diff=0 lossy=4706 fnv_ly=065927dd4d793a7d fnv_lypx=a8689aa48db264e2
libvpx    frames=10 bytes=10766 fnv_bit=62a63640d7690a11 dec_frames=10 fnv_px=f85eaa8153b093fc
openh264  frames=10 bytes=8619 fnv_bit=316f1b141efb69a7 dec_frames=10 fnv_px=762b92ca7ae625a5
libaom    frames=5 bytes=2683 fnv_bit=d74bacb1c99a8c30 dec_frames=5 fnv_px=ab53811322a88564
```

## 2. 五项共同的取态：关掉 x86/arm SIMD，纯 C/C++ 对照

这五项上游都自带 x86/ARM 汇编或 intrinsic，riscv 一个都没有。基线阶段统一：

- libvpx → `--target=generic-gnu`（configure 里没有 riscv，generic 就是纯 C）
- libaom → `AOM_TARGET_CPU=generic`（关掉全部 SIMD 与 runtime dispatch）
- openh264 → `USE_ASM=No`（汇编只有 x86/arm/loongarch）
- libwebp → 上游 C 实现本来就没有 riscv 分支，直接用
- opus → **必须定点**（`OPUS_FIXED_POINT=ON`）：浮点路径跨编译器会抖，定点才 bit-exact。
  另外 `--disable-intrinsics` 关掉 SSE/NEON 的运行时探测。

这样 native 与 riscv 走的是同一条 C 路径，A/B 才只差架构一个变量。将来接 RVV 内核时，
**只改 riscv 侧、native 侧保持 generic**，基线期望值就是这五行的哈希。

## 3. 复现

```bash
# 五项，逐工程
cd ~/work/<pkg>-rvv
./test/run_ab.sh              # native A/B（src vs baseline）
./scripts/cross-baseline.sh   # riscv64 交叉基线，打印两侧哈希并比对
```

镜像：libvpx / openh264 / libaom 用 `rvv-cross:2`（探针是 C++ 或 CMake 里带 CXX，需要 riscv g++），
opus / libwebp 用 `rvv-cross:1` 亦可。

## 4. webrtc-audio-processing 的卡点（未解，已定位）

1. **上游 examples 在 macOS 链接失败**（与本移植无关的 upstream bug）：
   `libwebrtc-audio-processing-2.a` 里的 `logging.cc` 引用 CoreFoundation 的
   `_CFBundleGetIdentifier` / `_CFBundleGetMainBundle` / `_CFPreferencesGetAppBooleanValue` /
   `___CFConstantStringClassReference`，`examples/run-offline` 链接不过。
   → 绕法已落地：只 `ninja` 库目标 + `meson install --no-rebuild`，库本身能编出来并安装。
2. **探针缺 absl 头/库**：APM 2.1 强依赖 abseil（`dependency('absl_base', version >= 20240722)`），
   meson 从 `subprojects/abseil-cpp.wrap` 拉 20240722.0 + wrapdb 补丁，**编译产物不 install**，
   所以 `pkg_apm.cpp` 里 `#include "absl/base/config.h"` 找不到。
   → 下一步：在 `cmake/pkg-build.sh` 里把 subproject 的 `absl/` 头与 `libabsl_*.a` 拷进
   `<out>/prefix`（或单独 cmake 编一份 abseil 进 prefix），再让 harness 链接。

## 5. 门禁与未做项（明确写清，避免误读为完成）

- 六项都有 `test/cases/01_*.sh`，`run_ab.sh` 判据是**产出文件逐字节一致**（不是"跑完没报错"）。
- **没有任何 RVV 内核代码**；`src/` 与 `baseline/` 内容等价（W1 已核查过同一做法）。
- qemu 上的耗时**不能**当性能结论，性能要等真机 `benchmark/pair_bench.sh`。
- 六项子模块已挂到主仓库 `projects/`，`data/status.csv` 中五项 `G2`、webrtc-ap `G1`（带 blocker）。
