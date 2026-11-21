# 第一轮内核实现状态（功能优先，不做优化）

真机 `10.91.8.28`（riscv64 / rv64gcv / VLEN=256 / gcc 15.2），口径：每包「写内核 → 编译 → 真机 A/B 位精确门禁 → 提交」。

## 1. 本轮新增/启用的内核

| 包 | 内核 | 接入方式 | 门禁 | 提交 |
|---|---|---|---|---|
| libgcrypt | `buf_xor` / `buf_xor_n_copy_2`（CBC 解密主路径，`src/riscv/buf_xor_rvv.h`，e8m1） | 头文件内 `#if defined(RVV_KERNELS) && defined(__riscv_v)` 分支，`len>=64` 走向量 | ALL PASS（2 用例） | `60b0acf` |
| zlib-ng | `adler32`（分块加权求和，`src/arch/riscv/adler32_rvv.h`，e8m1→u32 归约） | `adler32_c()` 入口早返回 | ALL PASS（2 用例） | `18ab427` |
| libvpx | `vpx_sad8/16/32/64`、`sse`（上游 `vpx_dsp/riscv/`，编译期接线） | `-DCONFIG_RVV_SAD=1 -DCONFIG_RVV_SSE=1` + `-march=rv64gcv` | ALL PASS（2 用例）；`nm` 证据：A 有 `vpx_sad16x16_rvv`，B 无 | `0e75558` |
| webrtc-ap | `WebRtcSpl_DotProductWithScale`（`webrtc/common_audio/signal_processing/riscv/dot_product_rvv.h`，i16→i32 宽乘 + 算术右移 + 归约） | `.cc` 入口早返回，`RVV_KERNELS` 宏控制 | ALL PASS（2 用例）；`build.ninja` 证据：A 含 `-DRVV_KERNELS=1`，B 不含 | `fe28be6` |
| cryptopp | `xorbuf`（就地 / 三缓冲 XOR，`src/riscv/xor_rvv.h`，e8m1） | `misc.cpp` 两个 `xorbuf()` 入口早返回 | ALL PASS（2 用例） | `122aab0` |
| nettle | `memxor`（`src/riscv/memxor_rvv.h`，e8m1） | `memxor.c` 的 `memxor()` 在 `n>=64` 时早返回 | ALL PASS（2 用例，`nettle-hash` 逐字节一致） | `06bf412` |
| botan | `xor_buf`（`src/src/riscv/xor_rvv.h`，e8m1） | `lib/utils/mem_ops.h` 两处 `xor_buf()` 早返回 | ALL PASS（2 用例） | `9cc68e1` |
| speexdsp | 窗函数应用（`src/libspeexdsp/riscv/window_rvv.h`，e32m4 逐元素乘） | `preprocess_analysis()` 的 windowing 循环（非定点构建下就是纯乘） | ALL PASS（`00_framework` + 新增 `speexdsp-echo` 真实用例） | `c80b0ab` |
| mpg123 | `dct64` 第一级蝶形（`src/src/libmpg123/riscv/dct64_rvv.h`，e32m1 + `vrgather` 反序） | `INT123_dct64()` 开头两个 16 长度循环 | ALL PASS（`00_framework` + 新增 `mpg123-decode` 真实用例，解码 PCM 逐字节一致） | `41c5850` |
| stockfish | NNUE `affine_transform_non_ssse3`（`src/src/nnue/layers/riscv/affine_rvv.h`，i8×u8→i32） | 新增 `cmake/pkg-build.sh` 走上游 Makefile（`ARCH=general-64`，命令行 `CXXFLAGS/LDFLAGS` 压掉 `-m64`）；用例 `stockfish-eval.sh` 跑 `eval` | ALL PASS（`00_framework` + `stockfish-eval`，评估输出逐字节一致） | `ebc8cda` |

十包都验证过"A 侧真的编进去了"（zlib-ng：`flags.make` 含 `RVV_KERNELS=1`；libgcrypt：`bufhelp.h` include + 355/433 行调用分支；libvpx：`nm` 符号计数 A=1 / B=0；botan：`pkg-build.sh` 的 `--extra-cxxflags` 多了 `-DRVV_KERNELS=1 -Isrc/riscv`；speexdsp/mpg123：`build/ab-a/pkg/src/config.log` 有 `-DRVV_KERNELS=1`，B 侧没有；stockfish：A 侧 `build.log` 里 27 条编译命令带 `-DRVV_KERNELS=1`）。

**本轮最贵的教训**：门禁 PASS 不等于内核生效。speexdsp/mpg123 第一版透传把 `CFLAGS=...` 拼进了 configure 参数，被拆成独立 argv 后 configure 直接吞掉，A 侧其实编的是原样 C 代码——第一次"PASS"是空内核的假绿。改成 `export CFLAGS="-O2 -march=... -DRVV_KERNELS=1"` 后，用 `config.log` 里的宏 + `objdump -d` 的 `vfmul`/`vrgather` 双向确认，才敢记成"落地"。

botan 的坑也值得记一笔：`configure.py` 会把公共头**拷进** `build/include/public/botan/`，任何相对路径 `#include "../../riscv/x.h"` 在副本里必然失效，只能改成裸文件名 `"xor_rvv.h"` 并靠 `-Isrc/riscv` 找头。

## 2. 启用即用（上游已自带 RVV 路径）

| 包 | 情况 | 提交 |
|---|---|---|
| pixman | 上游 `pixman-riscv.c` / `pixman-rvv.c` 由 meson 自带，且 meson 对 RVV 文件自己加 `-march=rv64gcv1p0`；A/B 两侧各 199 个 rvv 符号，说明**上游默认就编 RVV** | `4bed00c` |
| libjpeg-turbo | 上游 `simd/riscv64/*-rvv.c` 在两侧都已编入（各 95 个 rvv 符号），`WITH_SIMD=ON` 即可 | `ba91b22` |

这两包本轮只补了 `pkg-build.sh` 的 march/内核开关透传，**没有新增自写内核**——如实记在这里，避免把"上游自带"算成"本轮实现"。

## 3. 仍未写内核的包（2 个）

fftw、gromacs。逐个卡点（都是实测，不是推测）：

| 包 | 现有用例 | 卡点 |
|---|---|---|
| fftw | `01_fftw`（`fftw_harness` 已接，1024 点复 FFT + `FFTW_ESTIMATE`） | 用例在。1024=64×16，实际用的是 `n1_64`/`n1_16` 码本；`n1_2` 这种小码本根本不会被调度到，钩它等于空跑——必须按 FFTW 自己的分解表选码本，且要保持非 FMA 分支的运算顺序 |
| gromacs | `01_gromacs` | 实测该用例跑的是 `gmx editconf`（`tiny.gro` 进、`edited.gro` 出），**不是 mdrun**；因此内核点位必须在 editconf 的路径上（配箱/写结构），mdrun 侧的 `pbc_dx`、SETTLE 都跑不到 |

speexdsp / mpg123 / stockfish 这轮已经补完：两侧上游由 `cmake/pkg-build.sh` 各编一份（前两者 autotools、后者自带 Makefile），用例脚本放进 `test/cases/` 后门禁才真正有产物可比。

这批包的共同点是：`src/` 里既无 `rvv/`/`riscv/` 目录、也无 `RVV_KERNELS` 命中，内核要从零创建，且都走 `cmake/pkg-build.sh` 编上游，需要沿用本轮验证过的穿透范式：

- `upstream.cmake` 的 `add_custom_target(pkg ...)` 多传两个参数 `"${RVV_MARCH}" "$<IF:$<BOOL:${RVV_KERNELS}>,1,0>"`；
- `pkg-build.sh` 里 `MARCH=${3:-rv64gcv}; KERN=${4:-0}`，`KERN=1` 时把 `-march=${MARCH} -DRVV_KERNELS=1` 塞进 `CFLAGS`（meson 走环境变量，configure 走 `--extra-cflags`，CMake 走 `-DCMAKE_C_FLAGS`）；
- 内核头文件放 `src/<子目录>/riscv/<name>_rvv.h`，`#include` 必须在**文件头部**（放末尾会"先使用后声明"）；
- 每包先选一个**确定性热点**：speexdsp `filterbank_compute_psd16`、nettle `sha256_compress`、mpg123 `dct64`、fftw `n1_2/n1_4` codelet、stockfish `NNUE affine`、webrtc-ap `WebRtcSpl_DotProductWithScale`、gromacs `bonded` 角度项、botan/cryptopp 的块 XOR。

## 4. 遗留

- libaom、libde265 的上游 RVV 文件（`av1/common/riscv/`、`libde265/riscv/`）在 `src/` 里存在但**未进构建**（`CMakeLists.txt` 无 riscv 命中），需自己接线后才算落地。
- pixman/libjpeg-turbo 若要"自写内核"，得另选点位（上游已覆盖主要 fast path）。
