# G3 RVV 内核测试报告（2026-11-14）

## 1. 范围与口径

本轮按计划顺序从 W1 起推 G3，先做"上游已经自带 RVV 实现"的包：这类包的 G3 不是写内核，
而是**打开向量路径并对齐口径**。已排除 gdal / ceph（用户指示）。

A/B 口径（全部包统一）：

| 侧 | 配置 |
|---|---|
| A | `-march=rv64gcv`（或该包要求的 `rv64gcv1p0`），打开该包的向量实现 |
| B | **同一 march**，关掉向量实现（`rvv=disabled` / `WITH_RVV=OFF` / `WITH_SIMD=OFF`） |

唯一变量是向量开关；若 B 侧降 march，比出来的是"有向量 vs 没向量"，不能说明手写内核
相对编译器自动向量化的增益。功能门禁用 qemu 逐字节比对，浮点内核按相对误差 ≤1e-6。

## 2. 功能结果（已完成 3 项）

| 包 | 上游 RVV 规模 | A/B 开关 | 结果 |
|---|---|---|---|
| **pixman** | `pixman-rvv.c` 约 1500 行（fill/OVER 等整套） | `rvv` vs `rvv=disabled` | `fnv=066ba22180589ab5` 两侧一致 |
| **zlib-ng** | 4 个文件（adler32/chunkset/compare256/slide_hash） | `WITH_RVV` | `in=200003 out=73562 crc=2644adc5 fnv=3bb0c93b653afa83` 两侧一致 |
| **libjpeg-turbo** | 16 个文件（IDCT/FDCT/色彩/采样/量化） | `WITH_SIMD` | 码流 `fnv_jpeg=f0dd2e9ada7876e4`、像素 `fnv_px=79887ab513b04ba1` 两侧一致 |
| **libgcrypt** | 13 个文件（chacha20/poly1305/sha*/sm*/gcm/crc） | 默认 asm vs `--disable-asm` | `sha256=8ae5324f… fnv_ct=1b61c683d7e61c03` 两侧一致 |
| **libaom** | 11 个文件（convolve/compound/wiener/cdef，高低比特深） | `ENABLE_RVV` | 码流 `fnv_bit=d74bacb1c99a8c30`、像素 `fnv_px=ab53811322a88564` 两侧一致 |
| **libpng** | 7 个 row filter（up/sub/avg/paeth ×bpp） | `PNG_RISCV_RVV_IMPLEMENTATION` | `fnv_png=3bd158cdb34ca865`、`fnv_px=7322844870c2c46b` 两侧一致 |

三项都是**逐字节相同**。libjpeg-turbo 的码流也一致这一点值得记下：它的 SIMD 内核按
"与 C 参考实现逐位一致"设计（ISLOW 整数 IDCT、定点色彩转换），向量化不改变舍入，
所以这里不需要容差判据。

### 2.1 一个必须补的检查：变异测试

"宏打开了、代码也编了，但运行时仍走 C 路径"是这类包的典型假通过。libpng 就做了变异测试：
故意在 `png_read_filter_row_up_rvv` 的 `vse8` 后翻一个字节重编 A 侧，结果 harness 直接报
`pixel mismatch`（exit 11），正常 A 侧则通过——证明 RVV 内核确实被执行。
这一步已固化成 `libpng-rvv/scripts/mutation-check.sh`，其余"打开即用"的包应同样补一次。

## 3. 真机性能（SpacemiT K3 / Bianbu，<BOARD_HOST>）

板子：`Linux k3 6.18.3 riscv64`，8 核 / 16 GB，`isa` 含 `rv64imafdcvh` + RVV 1.0
（`zve32x/zve64d/zve64f`）+ 全套 `Zvk*`（`zvkned/zvknha/zvknhb/zvksh/zvkg/zvkb`）。
`/proc/cpuinfo` 未暴露 `vlenb`，VLEN 待另测。

方法：每包 A/B **交替 5 轮**，每轮内侧各跑 3 次取最优，取中位；全部 `-static`，
`data/board-ab.log` 为原始记录。

| 包 | 指标 | A（RVV/asm） | B（标量 C） | 加速比 |
|---|---|---|---|---|
| pixman | OVER 1024×1024 | 1.485 ms，706.2 mpx/s | 4.66 ms，225.1 mpx/s | **3.14×** |
| zlib-ng | adler32 16 MiB | 3.943 ms（0.235 ns/B） | 3.650 ms（0.218 ns/B） | **0.93×（慢 7%）** |
| zlib-ng | deflate 1 MiB | 10.24 ms | 12.33 ms | **1.20×** |
| libjpeg-turbo | 压缩 1024×768 q90 | 14.04 ms | 25.29 ms | **1.80×** |
| libjpeg-turbo | 解压 1024×768 | 13.16 ms | 20.57 ms | **1.56×** |
| libgcrypt | SHA-256 16 MiB | 1208.4 MBps | 100.8 MBps | **12.0×** |
| libgcrypt | AES-256-CTR 16 MiB | 2005.7 MBps | 50.9 MBps | **39.4×** |
| libpng | 解码 1024×768 | 3.69 ms | 3.81 ms | **1.03×** |
| libaom | — | 无 bench（5 帧 harness 太短） | — | — |

### 3.1 三个必须说清的口径问题

1. **libgcrypt 的 39× 不是纯 RVV**。`nm` 确认 A 侧编入了
   `_gcry_aes_riscv_zvkned_ctr_enc` 等 12 个 Zvkned 符号——K3 自带 `zvkned`，AES-CTR
   走的是加密扩展而非向量 gather；SHA-256 同理走 `zvknh`。加速比是"RVV + Zvk* 对 C"，
   报告里不能写成"RVV 让 AES 快 39 倍"。
2. **zlib-ng 的 adler32 RVV 比标量慢 7%**。三处证据一致（5 轮全部 on 更慢），
   不是噪声。adler32 是 8 bit 累加 + 少量 16 bit 进位，标量版在 8 核乱序核上已接近
   每周期 1 字节；RVV 版受 `vlenb` 与累加归约开销拖累。**这是"上游自带 RVV 也可能负优化"
   的第一个实证**，值得单独记档。
3. **libpng 只有 1.03×**。行过滤本身只占解码时间的一小块，主体是 inflate（两侧共用
   zlib-ng 的**标量**库）。要看到真实收益，得把 libpng 接上 zlib-ng 的 RVV 版本再测一次。

### 3.2 上板复现

```bash
~/work/rvv/scripts/board-ab.sh pixman <board-host>
```

板上路径 `/root/rvv-k/<pkg>/{on,off}/bench`，驱动 `/root/rvv-k/ab-run.sh`（交替 5 轮）。

## 4. 队列（按 SSE/NEON 规模与上游现状排）

上游已有 RVV（先"打开并验收"）：

| 包 | 状态 |
|---|---|
| pixman | 功能验收完成 |
| zlib-ng | 功能验收完成 |
| libjpeg-turbo | 功能验收完成 |
| libgcrypt | 功能验收完成 |
| libaom | 功能验收完成 |
| libpng | 功能验收完成（需手工接线，见 §2.1） |

**修正**：早先用 `grep -ri riscv` 统计时，eigen / gromacs / botan / cryptopp / openssl
被算成"已有 RVV"，复核后是误判——它们的 riscv 字样全部出现在 CI 脚本和测试文件里，
没有任何 `__riscv_v*` intrinsic 或 `riscv_vector.h`。所以真正"上游自带 RVV"的是
**6 个包**（pixman、zlib-ng、libjpeg-turbo、libgcrypt、libaom、libpng），现已全部功能验收。
其余 14 个都属于"要从零写内核"。

需要写内核（按收益排序）：

1. **libvpx**（SSE 196 / NEON 178 文件，体量最大）
2. **fftw**（88/74，codelet 结构特殊）
3. **openh264**（64/96，先 deblock+IDCT）
4. **cryptopp**（79/61，上游有 RISC-V 后端可先复用）
5. **libwebp**（45/40，先 YUV→RGB 与 fancy upsampling）
6. **opus**（44/62，先 NSQ）
7. **webrtc-ap**（45/52，先 resampler）
8. **zimg**（17/20，先 resize 水平卷积）
9. **x264**（24/19，先 SATD/SAD）
10. **libde265**（9/8，先 IDCT）
11. **botan / openssl**（AES/CTR；openssl 可先走 rv64gcv 汇编后端）
12. **eigen**（无上游 RVV，packet math 要自写，量大但模式清晰）
13. **gromacs**（无上游 RVV，G2 已用 GMX_SIMD=None，内核要自己起）

## 4.1 需要写内核的部分：libvpx 第一个内核（SAD）

libvpx 没有上游 RVV，第一个内核选了 SAD（逐像素绝对差和），语义最简、收益可量。
实现 `libvpx-rvv/src/vpx_dsp/riscv/sad_rvv.c`；验证用 `test/kernel_sad.c`，C 参照逐字
拷贝自上游 `sad()`，两侧只差 `-DUSE_RVV`，RVV 侧同时算 C 与 RVV 逐值比对（qemu 四档全一致）。

| 尺寸 | C | v1 每行归约 | **v4 混合分派（最终）** |
|---|---|---|---|
| 8x8 | 70.7 ns | 96.4 ns（0.73×） | **58.2 ns（1.21×）** |
| 16x16 | 236.3 ns | 251.4 ns（0.94×） | **108.4 ns（2.18×）** |
| 32x32 | 998.7 ns | 998.6 ns（1.00×） | **233.5 ns（4.28×）** |
| 64x64 | 3195.3 ns | 3196.2 ns（1.00×） | **903.3 ns（3.54×）** |

三处改动把这组数字从"有负优化"变成"全为正"：

1. **归约从每行一次改成整块一次**（u8 宽度累加进 u16 累加器，最后 `vwredsumu` 一次）；
2. **chunk 宽度按块大小分派**：宽 ≤16 用 u16m1 累加器（16 字节 chunk），宽 ≥32 用
   u16m2（32 字节 chunk）。统一 32 字节会让 16x16 退化到 1.94×；
3. **不假设 VLEN/MVL**：第一版直接用 `width` 当 vl，板上（VLEN=256）没事，
   qemu（VLEN=128）下 16x16 只算了一半（`c=22340/rvv=11170`），靠逐值差分才抓出来。

其他要点：u8 上不能直接 `abs(a-b)`（会回绕），用 `vmaxu/vminu` 相减；
`vwredsumu` 在 GCC 14 返回的是**向量**不是标量，还要 `vmv.x.s` 取值。
**已接到真实编码路径**（编译期开关 `CONFIG_RVV_SAD`，见 §4.2），编码器级 A/B 也有了。

## 4.2 libvpx 编码器级 A/B

内核数好看不等于编码器变快。接法是编译期开关：`src/vpx_dsp/sad.c` 加 `SAD_DISPATCH`，
打开 `CONFIG_RVV_SAD` 时 8/16/32/64 方形 SAD 走 RVV，其余尺寸与 `_avg`/`x4d` 仍走上游 C。
两套构建只差 `--extra-cflags` 里多一个 `-DCONFIG_RVV_SAD=1`（脚本 `scripts/g3-wire-ab.sh`）。

功能：qemu 下两侧跑既有 G2 探针（VP8 128×96 / 10 帧 / CBR / cpu-used=0），
`bytes=10766 fnv_bit=62a63640d7690a11 fnv_px=f85eaa8153b093fc` 完全一致，也与 G2 基线一致。

真机（K3，5 轮交替、每轮内侧 3 次取最优，整条"编码 10 帧 + 解码回环"墙钟）：

| 轮 | off（纯 C） | on（RVV SAD） |
|---|---|---|
| 1 | 587 ms | 526 ms |
| 2–5 | 589/587/587/586 | 527/527/527/526 |

**≈1.12×（快 11%）**，5 轮同向。

口径说明：128×96 小分辨率下 SAD 只占编码链的一部分（还有变换、量化、熵编码、
环路滤波和整个解码），1.12× 已是"只换一项"的合理量级；另外这是**编译期开关**——
本配置 `vpx_dsp_rtcd.h` 是 `#define vpx_sad16x16 vpx_sad16x16_c` 的编译期别名，
没有运行时函数指针可改。真正的 rtcd 运行时分发要改 `vpx_dsp_rtcd_defs.pl` 加检测链，
对 Gentoo rv64gcv 目标暂无必要，记为待办。

## 4.3 需要写内核的部分：openh264 第一个内核（SAD）

openh264 没有任何 RISC-V 后端（`USE_ASM=No` 时全走 C）。第一个内核同样选 SAD，
接线点是 `pfSampleSad[]` 函数指针表（`WelsInitSampleSadFunc`），
A/B 只差 `-DHAVE_RVV=1`（脚本 `scripts/g3-wire-ab.sh`）。

功能：qemu 下两侧都跑既有 G2 探针，`bytes=8619 fnv_bit=316f1b141efb69a7
fnv_px=762b92ca7ae625a5` 完全一致；符号核对 `on` 侧含 14 个 `*_rvv`、`off` 侧 0 个。

内核级真机（K3，300k 次/档）：

| 块 | C ns/call | RVV | 比值 |
|---|---|---|---|
| 4x4 | 21.8 | 34.9 | **0.62×（负优化）** |
| 4x8 | 45.5 | 57.4 | **0.79×（负优化）** |
| 8x4 | 45.4 | 34.6 | 1.31× |
| 8x8 | 78.1 | 57.3 | 1.36× |
| 16x16 | 302.6 | 103.9 | **2.91×** |

**决定因素是宽度不是面积**：宽 4 的块每次只有 4 字节进向量，`vsetvl` + 尾部归约
的固定开销盖过算术量。据此 `pfSampleSad[]` 只覆盖 16x16 / 16x8 / 8x16 / 8x8 / 8x4，
**4x4 与 4x8 保留 C**。

编码器级真机（5 轮交替、每轮内侧 3 次取最优）：35414–35563 us → 34781–34935 us，
**≈1.018×**，5 轮同向、波动 ≤0.1%。

为什么不亮眼：openh264 的亚分区搜索大量用 **4x4 SAD**，恰好是负优化那一档。
要在 openh264 上拿到明显收益，得做 4x4 批量化（一次算 4 块）或换 deblocking / IDCT。

## 5. 本轮顺带修掉的通用坑

`test/cpu_probe.c` 的 `vrgather` 微基准用有符号向量做索引，GCC 14 起
`__riscv_vrgather_vv_i32m2` 只接受 `vuint32m2_t`，RVV 目标下直接编不过。
已批量修掉 **20 个工程**的副本，并同步修进 Skill 模板 `assets/skeleton/test/cpu_probe.c`，
以后新建工程不会再带这个 bug。

## 4.4 libde265 add_residual（负结论，不升 G3）

`transform.cc:324` 是主反变换路径收尾，每块必调 `add_residual`，故先做它。内核
`src/libde265/riscv/add_residual_rvv.c`（i32m2 分块 + `vzext` + `vmax/vmin` 钳位 +
两级 `vnclipu`），`fallback.cc` 覆盖 `add_residual_8/16` 指针，A/B 只差 `-DHAVE_RVV=1`。

功能：qemu（VLEN=128）两侧 `dec frames=10 bytes=61440 fnv_px=cf67fb9981835c6a`，
与 G2 基线一致；`nm` 核对 on 侧有 rvv 符号、off 侧 0 个。

内核级真机（200k 次/档）：

| nT | C | RVV | 比值 |
|---|---|---|---|
| 4 | 49.4–53.2 ns | 57.7–58.1 ns | **0.86–0.92×** |
| 8 | 176.1–180.0 | 93.1–93.2 | **1.89–1.93×** |
| 16 | 626.9–727.2 | 186.3–186.7 | **3.37–3.90×** |
| 32 | 2584.3–2701.6 | 759.5–767.3 | **3.37–3.56×** |

整链（10 帧 64x64，同进程 300 轮，5 轮交替每轮 3 次取最优）：

| 侧 | total_us | 相对 off |
|---|---|---|
| off | 806.2–807.4 k | 1.000 |
| on（全尺寸 RVV） | 813.3–814.0 k | **0.991×** |
| on2（仅 ≥8x8 RVV） | 807.4–808.3 k | **0.999×** |

归因：①4x4 负优化吃掉全部收益（收窄后回到持平，与 openh264 同规律）；
②`add_residual` 在解码总时间占比 <1%，3.4× 摊不进整链 —— "每块必调"不等于"占比高"；
③C 侧被内联进 `transform_coefficients`，RVV 侧多一次指针调用，块越小越吃亏。

结论：代码保留在 `-DHAVE_RVV` 下（默认不编），**不升 G3**，下一轮换算术密集内核。

### 4.5 libde265 第二个内核：8×8 反变换（IDCT，正值）

`add_residual` 的负结论说明"每块必调"不等于"占比高"，于是换到算术密集的反变换。
关键观察是 `transform_idct_add` 的两通（V 通、H 通）是**同一个 nT×nT 基矩阵乘**，
只是输入不同，因此不需要转置也不需要 `vrgather`：

> 对输出下标 i 一次算 nT 个（一个向量车道）：`acc[i] = Σ_j mat[j][i] * s[j]`

矩阵从上游 `static int8_t mat_dct[32][32]` 在 `fact=4` 取行复制成 int32，setup 时一次。
接线 `transform_add_8[1] ← transform_8x8_add_8_rvv`（`transform.cc:324` 主路径自动生效）。

功能：qemu off/on 两侧 `fnv_px=cf67fb9981835c6a`，与 G2 基线逐字节一致；内核 bench
在 on 二进制里先把 `accel.transform_add_8[idx]` 与 `transform_8x8_add_8_fallback`
逐像素比对通过后才计时。

真机 K3（内核级 200k 次/档，走 `acceleration_functions` 指针，两侧各含一次间接调用）：

| nT | C | RVV | 比值 |
|---|---|---|---|
| 8 | 888–897 ns | 606–609 ns | **1.46–1.48×** |
| 16 | 6964–6978 ns | 5066–5091 ns | 1.38× |

整链（10 帧 64×64，同进程 300 轮，6 轮交替每轮 3 次取最优）：

| 侧 | total_us | 相对 off |
|---|---|---|
| off | 806.6–807.6 k | 1.000 |
| on（8x8 RVV） | 803.3–803.8 k | **1.004×（+0.4%，6/6 轮同向）** |

**16×16 的负结论（实现保留、不接线）**：

| 配置 | 整链 | 相对 off |
|---|---|---|
| 8x8 + 16x16 全量算 | 826.7–827.8 k | **0.975×** |
| 8x8 + 16x16（`nnz<=8` 走 C 门控） | 808.7–809.9 k | **0.997×** |

真实码流里 16×16 残差极稀疏，C 侧 `lastCol` 截断把每通从 nT 次乘法砍到 `lastCol+1` 次，
几乎免费；RVV 要么全量算 16 个 tap，要么先扫 256 个系数做门控，而 256 次 load/compare
比它想省的 16 次乘法贵一个量级。**要救 16×16/32×32，必须先让上层把 nnz/lastCol
传下来（改函数签名），否则门控成本大于收益。**

一并记档的一条口径问题：8x8-only 版本曾有一次测得 806.2→785.9 k（1.026×），
重建同配置二进制复测稳定回到 803.5 k，该读数按"不可复现"作废，只采信 1.004×。
