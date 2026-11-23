# 第一轮内核实现状态（功能优先，不做优化）

真机 `<device>`（riscv64 / rv64gcv / VLEN=256 / gcc 15.2），口径：每包「写内核 → 编译 → 真机 A/B 位精确门禁 → 提交」。

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

| gromacs | SETTLE 约束（`src/src/gromacs/mdlib/riscv/settle_rvv.h`，e32m1 × 8 lane） | `settle.cpp` 的 `settleTemplate` 在 `packSize == 1` 时早返回并调 `settle_rvv`；PBC 折返**逐 lane 调标量 `pbc_dx_aiuc`** 保位精确 | ALL PASS（`01_gromacs`：`confout.gro` / `traj.trr` 两侧 `cmp` 一致） | `7f025fe` |

十一包都验证过"A 侧真的编进去了"（zlib-ng：`flags.make` 含 `RVV_KERNELS=1`；libgcrypt：`bufhelp.h` include + 355/433 行调用分支；libvpx：`nm` 符号计数 A=1 / B=0；botan：`pkg-build.sh` 的 `--extra-cxxflags` 多了 `-DRVV_KERNELS=1 -Isrc/riscv`；speexdsp/mpg123：`build/ab-a/pkg/src/config.log` 有 `-DRVV_KERNELS=1`，B 侧没有；stockfish：A 侧 `build.log` 里 27 条编译命令带 `-DRVV_KERNELS=1`；gromacs：`settle.cpp.o` 反汇编 1115 条向量指令，且扰动探针实测生效）。

**本轮最贵的教训**：门禁 PASS 不等于内核生效。speexdsp/mpg123 第一版透传把 `CFLAGS=...` 拼进了 configure 参数，被拆成独立 argv 后 configure 直接吞掉，A 侧其实编的是原样 C 代码——第一次"PASS"是空内核的假绿。改成 `export CFLAGS="-O2 -march=... -DRVV_KERNELS=1"` 后，用 `config.log` 里的宏 + `objdump -d` 的 `vfmul`/`vrgather` 双向确认，才敢记成"落地"。

botan 的坑也值得记一笔：`configure.py` 会把公共头**拷进** `build/include/public/botan/`，任何相对路径 `#include "../../riscv/x.h"` 在副本里必然失效，只能改成裸文件名 `"xor_rvv.h"` 并靠 `-Isrc/riscv` 找头。

## 2. 启用即用（上游已自带 RVV 路径）

| 包 | 情况 | 提交 |
|---|---|---|
| pixman | 上游 `pixman-riscv.c` / `pixman-rvv.c` 由 meson 自带，且 meson 对 RVV 文件自己加 `-march=rv64gcv1p0`；A/B 两侧各 199 个 rvv 符号，说明**上游默认就编 RVV** | `4bed00c` |
| libjpeg-turbo | 上游 `simd/riscv64/*-rvv.c` 在两侧都已编入（各 95 个 rvv 符号），`WITH_SIMD=ON` 即可 | `ba91b22` |

这两包本轮只补了 `pkg-build.sh` 的 march/内核开关透传，**没有新增自写内核**——如实记在这里，避免把"上游自带"算成"本轮实现"。

## 3. 原卡点（均已解除，记录留档）

fftw、gromacs 都属于"原先没写内核"的包，现已各自落地（fftw `68a25f9`、gromacs `7f025fe`）。当时实测的卡点：

| 包 | 现有用例 | 卡点 |
|---|---|---|
| fftw | `01_fftw`（`fftw_harness` 已接，1024 点复 FFT + `FFTW_ESTIMATE`） | 用例在。1024=64×16，实际调度 `n1_64`/`n1_16` 码本；`n1_2` 不会被调度，钩它等于空跑。**实测 `fftw_print_plan` 结果：整条计划只用 `n1_32`（1024 = 32×32）**，`n1_16`/`n1_2` 都不会被调度。决定：按 `n1_32` 的批循环做 RVV（`vlse32` 跨批取数），照抄非 FMA 分支的运算顺序 |
| gromacs | `01_gromacs`（`gmx editconf`） | 实测该用例跑的是 `gmx editconf`，**不是 mdrun**；editconf 主路径只有坐标平移/包围盒统计和 `%8.3f` 输出，没有可位精确向量化的浮点热点，`pbc_dx` 也只被 domdec 用到。**决定：把用例扩成一次极短 mdrun，内核放 SETTLE 约束（逐分子独立、无跨分子累加，可位精确）** |

speexdsp / mpg123 / stockfish 这轮已经补完：两侧上游由 `cmake/pkg-build.sh` 各编一份（前两者 autotools、后者自带 Makefile），用例脚本放进 `test/cases/` 后门禁才真正有产物可比。

这批包的共同点是：`src/` 里既无 `rvv/`/`riscv/` 目录、也无 `RVV_KERNELS` 命中，内核要从零创建，且都走 `cmake/pkg-build.sh` 编上游，需要沿用本轮验证过的穿透范式：

- `upstream.cmake` 的 `add_custom_target(pkg ...)` 多传两个参数 `"${RVV_MARCH}" "$<IF:$<BOOL:${RVV_KERNELS}>,1,0>"`；
- `pkg-build.sh` 里 `MARCH=${3:-rv64gcv}; KERN=${4:-0}`，`KERN=1` 时把 `-march=${MARCH} -DRVV_KERNELS=1` 塞进 `CFLAGS`（meson 走环境变量，configure 走 `--extra-cflags`，CMake 走 `-DCMAKE_C_FLAGS`）；
- 内核头文件放 `src/<子目录>/riscv/<name>_rvv.h`，`#include` 必须在**文件头部**（放末尾会"先使用后声明"）；
- 每包先选一个**确定性热点**：speexdsp `filterbank_compute_psd16`、nettle `sha256_compress`、mpg123 `dct64`、fftw `n1_2/n1_4` codelet、stockfish `NNUE affine`、webrtc-ap `WebRtcSpl_DotProductWithScale`、gromacs `bonded` 角度项、botan/cryptopp 的块 XOR。

## 4. 遗留

- libaom、libde265 的上游 RVV 文件（`av1/common/riscv/`、`libde265/riscv/`）在 `src/` 里存在但**未进构建**（`CMakeLists.txt` 无 riscv 命中），需自己接线后才算落地。
- pixman/libjpeg-turbo 若要"自写内核"，得另选点位（上游已覆盖主要 fast path）。

## 5. 更新（本轮推进）

- **fftw 完成**（子模块 `68a25f9`）：靶点由 `fftw_print_plan` 实测确定为 **`n1_32`（整条计划只有它，1024 = 32×32）**。内核 `src/dft/scalar/riscv/n1_32_rvv.h` 把 32 个批铺到 8 条 lane（e64m2），输入按批步长 gather 成 SoA，码本语句体逐字照抄非 FMA 分支（只把 `ri/ii[WS(is,k)]`、`ro/io[WS(os,k)]` 换成 `RIk/IIk/ROk/IOk`），输出 scatter 回去。`cmake/pkg-build.sh` 加 `MARCH/KERN` 两个位置参数并 `export CFLAGS`（autotools 只认环境变量），`cmake/upstream.cmake` 用 generator expression 传参。
  - 门禁：A/B 逐字节一致（`dft1024 max_rel=3.112e-14 fnv=7c2af68f8fe41f90` 两侧相同）。
  - 生效证据：A `config.log` 有 `-DRVV_KERNELS=1`、B 没有；A 的 `n1_32.o` 反汇编 150 条向量指令且有 `n1_32_rvv` 符号，B 为 0。
  - 踩坑：① 抽取函数体时截断在 1310 行，漏掉末尾 6 行（正是 `os,11` / `os,27` 两组 store），表现为这两个输出点为 0、`max_rel=1.0`；`k%32 ∈ {11,27}` 全部错就是它的指纹。② 码本用 `E T...` 声明，向量化时要一并改类型；`ri[0]/ii[0]` 与 `WS(is,0)` 写法不同源，两种都要映射。③ 生成的头文件花括号比原函数少/多一层会报 "invalid storage class for function" 的误导性错误。

## 6. gromacs 用例迁移 + SETTLE 内核（已完成）

- 提交 `113fe1c`：`01_gromacs` 从 `gmx editconf` 改为 `grompp` + 20 步 `mdrun`，产出 `confout.gro`(255 B) 与 `traj.trr`(384 B) 的字节哈希；连跑两次 `cmp` 一致，**用例已可作逐字节门禁**。
- 迁移踩坑（全部实测）：① 原 `tiny.gro` 只有 4 个原子（第二个水分子缺 HW1/HW2），mdrun 无法接受，新建 `test/data/tiny-water.gro`（单分子、2 nm 盒）；② 新版上游删了顶层 `spc.itp`，须 `oplsaa.ff/forcefield.itp` + `oplsaa.ff/spc.itp`；③ `constraint-algorithm` 不是合法 mdp 项（水自动走 SETTLE）；④ cutoff 1.0 nm 配 2.0 nm 盒触发“超过最短盒向量一半”，改 0.9；⑤ `GMX_THREAD_MPI=OFF` 下 `mdrun -nt` 直接致命报错；⑥ **`gen-vel=yes` 默认随机种子** → 必须 `gen-seed = 1234`，否则两次运行第 3 行坐标就不同（曾误判为 mdrun 不确定）。
- **内核落地**（子模块 `7f025fe`）：`src/src/gromacs/mdlib/riscv/settle_rvv.h`，8 lane（`vector_size(32)` float），AoS 坐标按 stride 3 gather/scatter，Step1–Step5 + 速度更新完整照抄；`gmx::invsqrt` / `gmx::fma` / `max` **逐 lane 调标量实现**保舍入；virial 按分子顺序逐 lane 累加（不跨 lane 归约）。PBC 折返**逐 lane 调标量 `pbc_dx_aiuc`**，门控简化为 `packSize == 1`。
  - 门禁：`confout.gro` / `traj.trr` 两侧 `cmp` 一致（`confout_fnv=4ce190c207869f57`、`traj_fnv=e7ef2a091985cf81`）。
  - 生效证据（这轮最硬的一条）：`settle.cpp.o` 反汇编 1115 条向量指令 → 又做了**扰动探针**——把内核写回加 `1e-6f` 后增量重编，`confout` 哈希立刻变成 `4b3d04593a8e6fbd`，还原后回到 `4ce190c2…`。这是"内核真被执行"的直接证据，不再是符号/反汇编层面的推断。
  - 踩坑（全部实测）：① `pkg-build.sh` 把两个 `-D` 拼成**一个 argv**（`EXTRA="-DCMAKE_C_FLAGS=… -DCMAKE_CXX_FLAGS=…"`），cmake 把第二段当成第一个的值 → `CMAKE_CXX_FLAGS` 从未生效，内核压根没编进去，A/B 哈希"一致"其实是同一份标量代码（**同类空内核假绿的第二次现形**）。改成 bash 数组 `EXTRA=(-DCMAKE_C_FLAGS="${CMF}" -DCMAKE_CXX_FLAGS="${CMF}")` 后 `CMakeCache.txt` 才出现 `-march=rv64gcv -DRVV_KERNELS`。② `#include` 必须移到 `SettleData` / `SettleParameters` / `gmx::fma` / `pbc_dx_aiuc` 的声明**之后**（原位置在第 56 行，一开宏就是十几条 "not declared"）。③ `OUT` 传相对路径时，脚本 `cd "${OUT}/src/pkg"` 后再用 `${OUT}/bld` → 构建目录被解析到 `pkg/src/pkg/build/…`，`ninja` 找不到；脚本已加 `OUT=$(realpath "${OUT}")`。④ `pkg-build.sh` 会把 `src/` 拷进 `OUT/src/pkg` 再编，**改源码树不会触发重编**（对比时务必动副本，或用 `ninja -t commands` 看真命令行）。
