# W2 交叉编译基线（6 项全绿，且全部在 Linux 容器内编译）

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
| media-libs/webrtc-audio-processing | `webrtc-ap-rvv` | meson + abseil 20240722.0 wrap | APM 48 kHz/10 ms ×200 帧 | **全字段一致**（见 §4） |

实测输出（可直接作为后续回归的期望值）：

```
opus      frames=120 bytes=19200 fnv_bit=a04caa33e5671901 pcm=115200 fnv_pcm=74bc2325f58a2e04 ver=libopus unknown-fixed
libwebp   size=133x101 lossless=30026 fnv_ll=69c27e48073e9609 px_diff=0 lossy=4706 fnv_ly=065927dd4d793a7d fnv_lypx=a8689aa48db264e2
libvpx    frames=10 bytes=10766 fnv_bit=62a63640d7690a11 dec_frames=10 fnv_px=f85eaa8153b093fc
openh264  frames=10 bytes=8619 fnv_bit=316f1b141efb69a7 dec_frames=10 fnv_px=762b92ca7ae625a5
libaom    frames=5 bytes=2683 fnv_bit=d74bacb1c99a8c30 dec_frames=5 fnv_px=ab53811322a88564
webrtc-ap frames=200 pcm=96000 fnv_pcm=05ec2f7d501cd053 energy=8714.207510
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

**本机（macOS）不编译任何东西，只当编辑器。** native 与交叉两侧都在 Linux 容器里做，
两侧共享同一 glibc 与工具链，差异只剩架构本身。

```bash
cd ~/work/<pkg>-rvv
./scripts/native-baseline.sh   # native A/B（src vs baseline），在容器内跑 run_ab.sh
./scripts/cross-baseline.sh    # riscv64 交叉基线，qemu-user 跑探针，打印两侧哈希
```

镜像：libvpx / openh264 / libaom / webrtc-ap 用 `rvv-cross:2`（有 riscv g++）；
opus / libwebp 用 `rvv-cross:1` 亦可。

### 3.1 为什么不许在宿主上编

- 宿主是 macOS：`webrtc-ap` 的 upstream `examples/run-offline` 在 macOS 上缺 CoreFoundation
  符号（`_CFBundleGetIdentifier` 等），这是宿主平台的链接问题，与移植无关。换 Linux 容器后
  整个问题消失，不必给上游打补丁。
- native 与 riscv 同 glibc/同编译器版本，A/B 与交叉比对才有意义；混用宿主与容器会出现
  "同一份源码两个 C 库版本"的伪差异。
- 骨架的 `run_ab.sh` 曾在 Ubuntu 上假绿：`/bin/sh` 是 dash，用例开头 `set -euo pipefail` 直接
  失败 → 全部用例记 SKIP → 打印 "ALL PASS（0 个用例）"。现已改为 `run bash`，SKIP 计 FAIL。

## 4. webrtc-audio-processing：四个坑与解法（已全绿）

1. **宿主编译带来的假问题**：`examples/run-offline` 在 macOS 上缺 CoreFoundation 符号
   （`_CFBundleGetIdentifier` / `_CFBundleGetMainBundle` 等）。改成容器内编译后不复现；
   交叉侧仍只编库目标 + `meson install --no-rebuild`，不去碰 examples。
2. **abseil 只 install 头、不 install 库**：meson 子项目把 `absl/*` 头装到 `prefix/include`，
   静态库留在 build 树的 `*.a.p/` 里。直接 `cp libabsl_base.a` 出来用会踩下一条。
3. **meson 静态库是 thin archive**：成员按相对路径记录，`cp` 到别处后 `ar` 报
   `No such file or directory`，`ar x` 也不支持 thin。解法是**从各 `*.a.p/*.o` 重新
   `ar rcs libwebrtc-ap-full.a`**，并收全部上游静态库（APM 之外还有 isac/rdft，否则链接缺
   `WebRtc_rdft` / `WebRtcIsac_*`）。
4. **交叉文件的两个细节**：`exe_wrapper` 必须写数组并带 sysroot
   （`['qemu-riscv64','-L','/usr/riscv64-linux-gnu']`），否则 meson 报
   `Executables created by c compiler are not runnable`；`StreamConfig` 是 2 参（无第三参 `false`）。

结论：`frames=200 pcm=96000 fnv_pcm=05ec2f7d501cd053 energy=8714.207510`，riscv64 与 native
**逐字段一致**（含 float 打印的能量值）。

## 5. 门禁与未做项（明确写清，避免误读为完成）

- 六项都有 `test/cases/01_*.sh`，`run_ab.sh` 判据是**产出文件逐字节一致**（不是"跑完没报错"）。
- **没有任何 RVV 内核代码**；`src/` 与 `baseline/` 内容等价（W1 已核查过同一做法）。
- qemu 上的耗时**不能**当性能结论，性能要等真机 `benchmark/pair_bench.sh`。
- 六项子模块已挂到主仓库 `projects/`，`data/status.csv` 中六项全部 `G2`。
- 12 项（W1+W2）的 native A/B 与 riscv64 交叉基线现**全部在 Linux 容器内**跑通；
  哈希比对的唯一非逐字节项是 libpng 的 zlib 提供方差异（见 `docs/10-cross-baseline.md` §5）。
