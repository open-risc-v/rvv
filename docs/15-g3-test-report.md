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
| crypto++ | AES-256-CTR 64 KiB | **0.302 ms**（三轮全 0.302） | 0.951 ms（0.951/0.951/0.976） | **3.15×** |
| crypto++ | AES-256-CBC 64 KiB | **0.313 ms** | 0.982 ms | **3.14×** |
| crypto++ | AES-128-CTR 64 KiB | **0.226 ms** | 0.734 ms | **3.25×** |
| openssl | AES-256-GCM 64 KiB | **0.035 ms** | 9.905 ms | **≈287×** |
| openssl | SHA-512 64 KiB | **0.099 ms** | 0.368 ms | **≈3.7×** |

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

**第二轮扩容（8 个）**，两个新增都不是 intrinsics，因此都没被上面的 grep 抓到：

- **openssl**：perlasm 层自带 `aes-riscv64-zvkned*.pl`、`sha256-riscv64-zvknha*.pl`、
  `sha512-*zvknhb*.pl`，target `linux64-riscv64` 即自动编入（见 §4.12）。真机 CBC 138×、CTR 284×。
- **eigen**：`Eigen/src/Core/arch/RVV10/`（10 个文件）自带 packet math 后端，开关
  `EIGEN_RISCV64_USE_RVV10`，门控 `defined(__riscv_v_fixed_vlen)`。**已打通**：GCC 13 不认
  `-mrvv-vector-bits`（所以只能靠 `-D__riscv_v_fixed_vlen=256` 硬注入，又因 GCC 13 忽略
  `riscv_rvv_vector_bits` 属性而报 `member variables cannot have RVV type`）；**GCC 14 起认该选项**，
  配合 `-march=rv64gcv_zvl256b` 即可由编译器给出 `__riscv_v_fixed_vlen 256`。真机 GCC 15.2 原生
  编译，imatmul 9.4×、dmatmul 17.6×，两侧逐字节一致（见 §4.14）。

这把普查判据也补全了：`grep -rl "__riscv_v\|riscv_vector"` 只覆盖 intrinsics，
**perlasm 类包（openssl / x264 / libvpx / ffmpeg）必须另查 `*/asm/*riscv*`**，
**头文件门控类包（eigen）必须另查 `arch/*/` 目录与 `*_USE_*` 开关**。

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

### 4.6 x264：8bit SAD / SSD（目前整链收益最大）

x264 的 ME 主循环每候选 MV 都要算 SAD，16x16/8x8 是最高频两档；这也是本工程第四次
做 SAD 族内核（libvpx 4.28×、openh264 2.91×），设计可直接复用。

接线：`pixf->sad[]` / `sad_x3[]` / `sad_x4[]` / `ssd[]` 四张表在纯 C 构建下由
`PIXEL_SAD_C` 静态函数填充，所以只覆盖指针即可，不改 Makefile。两个必须注意的门：

1. **不能用 `HAVE_RVV` 这个宏名** —— x264 的 `configure` 生成 `config.h` 并写死
   `#define HAVE_RVV 0`，命令行 `-DHAVE_RVV=1` 被覆盖（只报 redefined 警告），内核
   静默不编译、`nm` 符号数为 0。改用 `HAVE_RVV_KERNELS`。
2. **必须限定 `BIT_DEPTH == 8`** —— `pixel.c` 编两遍（`pixel-8.o`/`pixel-10.o`），
   高比特深度时 `pixel` 是 `uint16_t`。

内核沿用已验证的两条修正：整块末尾一次归约（u8 差 `vmaxu/vminu/vsub` + `vwaddu.wv`
进 u16，末尾 `vwredsumu.vs`）；vl 取块宽而**不假设 VLEN/MVL**。

真机 K3 内核级（100k 次/档，3 轮）：

| 算子 | 尺寸 | C | RVV | 比值 |
|---|---|---|---|---|
| SAD | 16x16 | 340–349 ns | 57.8–58.9 ns | **5.81–5.98×** |
| SAD | 8x8 | 116–118 ns | 35.4 ns | **3.27–3.33×** |
| SSD | 16x16 | 290–292 ns | 142.7–143.7 ns | **2.02–2.04×** |
| SSD | 8x8 | 104–105 ns | 77.5–77.6 ns | **1.34–1.35×** |

整链（`veryfast` + HEX ME + CRF 23，单线程，每轮 2 次取最优）：

| 分辨率/帧数 | off | on | 比值 |
|---|---|---|---|
| 352×288 / 30 帧（6 轮） | 416.7–419.8 ms | 332.8–339.8 ms | **1.24–1.26×（均值 1.249×）** |
| 640×480 / 20 帧（3 轮） | 665.9–672.9 ms | 540.4–547.9 ms | **1.228–1.232×** |

两侧码流逐字节一致（352×288 `bytes=242393 fnv_bit=2c6e38b64b86a1cc`，
640×480 `bytes=461071 fnv_bit=9be77e95e98aedb9`）。

**这条是本工程到目前最强的整链收益**，与 libde265 §4.5 的 +0.4% 形成直接对照：
决定整链增益的不是内核倍数，而是该算子在真实管线里的占比。SAD 在 ME 里占比高、
16x16 内核本身又有 6×，所以能到 1.25×。

未做：`satd`（`--subme ≥ 4` 时比 SAD 更热，需要 4x4/8x8 Hadamard 与 `abs2` 打包）、
4x16 尺寸、10bit 路径、运行时 CPU 探测。

### 4.7 opus：celt_pitch_xcorr（内核 5.6× / 整链 1.005×）

`celt_pitch_xcorr` 是上游注释点名的 "the kernel you really want to optimize"，
x86/ARM 都有同名参照。接口固定：`xcorr[i] = Σ_j x[j]*y[i+j]`（定点 int16→int32，
并返回 maxcorr）。

接线：新增 `src/celt/riscv/pitch_xcorr_rvv.c`，由 `celt/pitch.c` 同 TU include；
`pitch.h` 里 `OVERRIDE_PITCH_XCORR` + 宏重定向，仅 `FIXED_POINT` 生效。
**定点下 `celt_pitch_xcorr_c` 有返回值 maxcorr（初值 1）**，宏必须用逗号表达式透传，
否则 `pitch_search` 报 "void value not ignored"。

设计要点：**4 个 lag 同时算、共用一份 x 装载**（与上游 `xcorr_kernel` 的 4-sum 结构
对齐）——这是主要收益来源，单 lag 版只有 ~2×。归约一次到位（`vwmacc` 加宽累加 +
末尾 `vredsum`）。

真机 K3 内核级（300 次/档 ×2）：

| len | max_pitch | C | RVV | 比值 |
|---|---|---|---|---|
| 480 | 1024 | 296–299 µs | 52.5–53.3 µs | **5.60–5.64×** |
| 240 | 512 | 74.7–75.0 µs | 14.6 µs | **5.13×** |
| 120 | 256 | 18.9 µs | 4.6–4.8 µs | **3.95–4.13×** |

整链（120 帧 48 kHz 定点编码，5 轮交替、内侧 3 次取最优）：off 130.94/131.06/130.99/
130.99/131.03 ms → on 130.30/130.19/130.30/130.41/130.34 ms，**≈1.005×**（5/5 同向）。

**归因（写清楚，避免误读）**：pitch search 走降采样后的 4 倍域，实际调用是
`len>>2=120`、`max_pitch>>2=256`，C 版每次只要 ~19 µs、一帧一次左右，120 帧合计
约 2.3 ms（占 131 ms 的 1.7%），内核吃掉其中 80%，上限 ~1.4%，实测 0.5%。
这条比 libde265 的 IDCT 更极端地印证了那条规律：**整链增益 ≈ 内核倍数 × 管线占比**。

opus 真正的时间大头是 MDCT/FFT 与 `comb_filter`，不是"简单内核"，本轮不碰；
`xcorr_kernel`（`len = ord` 只有 16–24）按"宽度决定收益"的既有结论也不做。

### 4.8 libwebp：编码器 SSE 代价函数（内核 1.81× / 整链 1.009×）

`VP8SSE16x16/16x8/8x8/4x4` 是有损编码 RD 循环里的代价函数，上游 `enc_sse2.c` /
`enc_neon.c` 都有同名实现，接口 `int (const uint8_t*, const uint8_t*)` + `BPS=32`
固定步长，属于 SAD/SSD 家族。

接线：`src/dsp/enc_rvv.c` 由 `enc.c` 同 TU include，`VP8EncDspInit()` 末尾覆盖指针。
两个形态问题：**DSP init 是惰性的**（只在第一次编码时触发，内核 bench 必须先手动调
`VP8EncDspInit()`，否则读到的指针是 NULL 直接段错误）；静态链接还需 `libsharpyuv.a`。

真机 K3 内核级（200k 次/档 ×2）：16x16 **1.80–1.81×**、16x8 **1.57×**、
8x8 **1.23–1.24×**、4x4 **1.06×**。

整链（512×384 q=75 method=4 有损编码，5 轮交替）：

| 配置 | off | on | 比值 |
|---|---|---|---|
| 四张表全接 | 126.4–127.5 ms | 130.5–131.2 ms | **0.968×（退化）** |
| 只接 16x16 / 16x8 | 126.5–127.8 ms | 125.5–126.4 ms | **≈1.009×**（均值 127.12 → 126.01） |

码流两侧一致（`bytes=34188 fnv=a69caad683943683`）。

**结论**：必须按宽度收窄派发——4x4 是 RD 里调用最多的一档，但只有 4 个 lane，
`vsetvl+vle` 的固定开销把 1.06× 的收益全吃掉，全开时整链 -3.2%。这与 openh264 的
4x4/4x8 保留 C 是同一结论，**已经是第二次独立验证**。收窄后 +0.9%，属于"弱正值，
可保留但收益有限"，与 libde265 IDCT 的 +0.4% 同类。

**测量坑（必须记）**：内核 bench 最初用 `(void)sse_c(...)` 丢弃结果，`-O2` 把整个
C 循环删掉，四个尺寸都测出恒定 45.6 ns（只剩两次 `clock_gettime` 的开销），而 RVV
侧因为走函数指针没被删，于是读出 0.24× 的假负优化。**纯函数计时必须用 `volatile`
sink 接住返回值**——这条会影响之后所有内核 bench。

### 4.9 zimg：垂直 resize 定点卷积（内核 7.6× / 整链 2.02×）

zimg 的 resize 分水平/垂直两遍，都是 `filter_width` 个 tap 的加权和。垂直那遍输出列连续、
每个输出行只换一组系数，是"多行按列加权求和"，向量化维度是列，结构最干净；bicubic 每输出
像素要读 4 个源行，所以它就是整条 resize 的主体。本轮只做垂直，水平留 C。

**接线成本主要在上游构建系统**：zimg 的 SIMD 分支是 configure 时按 `host_cpu` 写死的
（`ZIMG_X86`/`ZIMG_ARM`），RISC-V 上原本一条分支都没有。改动：`configure.ac` 的 `AS_CASE`
加 `riscv64` + `AC_DEFINE([ZIMG_RVV])` + `AM_CONDITIONAL([RVVSIMD])`；`Makefile.am` 的
`if RVVSIMD` 里加源文件；`cpuinfo.h` 的 `CPUClass` 加 `RISCV_RVV`；`resize_impl.cpp` 加分派。

A/B 口径：两侧同 `-march=rv64gcv`，唯一变量 `--disable-simd`——在 RISC-V 上它就等于
"有没有 RVV 内核"，因为上游没有别的 RISC-V SIMD。

真机 K3（bicubic，GRAY16）：

| 场景 | C | RVV | 比值 |
|---|---|---|---|
| 内核级：纯垂直 1920×1080→1920×720 | 23.534–23.573 ms | **3.096–3.103 ms** | **7.57–7.62×** |
| 水平对照 1920×1080→1280×1080 | 25.69–25.76 ms | 25.69–25.76 ms | 1.00×（未向量化） |
| 整链 1920×1080→1280×720 | 40.96–41.45 ms | **20.35–20.40 ms** | **2.01–2.03×** |

三种场景输出哈希分别恒为 `8ae2d305d97f41c5` / `fdbfc49578568fcf` / `3f41cccccde96e72`，
C 与 RVV 逐字节一致（1.14 定点运算位精确）。整链 41.0 → 20.3 ms 与"只砍掉垂直那遍
（省 20.4 ms）、水平 25.7 ms 原地不动"的算术完全对得上，归因闭合。

**这是本次 G3 整链收益最高的一个包**（此前 x264 1.249×、libvpx 1.12×、libwebp 1.009×、
opus 1.005×），原因是 resize 的垂直那遍本来就占了 zimg 一半的时间，且它的数据布局天然
适合 RVV（列连续、系数每行一组）。

**口径教训（必须记）**：第一版 `create()` 只要不是水平方向就直接建 RVV 实现，忽略了
`cpu` 参数，于是 `ZIMG_CPU_NONE`（约定是"可移植 C 路径"）也在跑 RVV，真机上出现
`on-none == on-auto == 20.3 ms` 而 `off ≈ 41 ms` 的怪现象——看上去像 2×，实际是"两份二进制
都在跑 RVV，只是 off 那份根本没编进去"。修正后 CPU_NONE 回落 C，才是干净的三方对照。
**A/B 里"关掉"的那一侧必须真的关掉，CPU 参数属于口径不是提示。**

另两个坑：`vnclipu_wx_u16m1` 的源必须是 `vuint32m2_t`（传 `vint32m2_t` 在 GCC 13 报类型错，
先 `vreinterpret_v_i32m2_u32m2`）；`m_pixel_max{ (1UL << depth) - 1 }` 在花括号初始化里触发
`-Wnarrowing`（=error），要 `static_cast<uint32_t>`。

剩余可做的：**水平 resize 的 RVV 版**（25.7 ms 是整链另一半，下一个最有价值的目标）、
FLOAT 路径、`depth`/`colorspace` 模块、运行时 CPU 探测。

### 4.10 zimg 水平 resize（内核 2.67× / 整链 4.24×）

§4.9 只做了垂直方向，整链停在 2.02×。水平那遍的 25.7 ms 是剩下的一半，本轮补上。

**难在数据布局**：垂直的每个 tap 是一整行、按列连续；水平是 `src[left[j] + k]`，
起点 `left[j]` 随输出列变化，必须 gather。上游 x86 AVX2 用预排 permute 表
（`resize_line_h_perm_u16_avx2`，把 `src[left..left+24]` 重排成 8 lane 再 `vpmaddwd`）；
RVV 有原生索引装载，直接用 `vluxei32` 逐像素 gather，省掉预处理表。

实现要点：一次 `vsetvl_e16m1` 取 16 个输出列（VLEN=256）；`filter.left` 用 `vle32` 装载并
左移 1 位转字节偏移；每个 tap `idx = leftv + 2k` → `vluxei32` 取像素 → 减 32768 →
`vreinterpret i16m1`；系数必须 `vlse16` 跨步取（`stride_i16 != filter_width`，
按连续向量读会串到下一行）；`vwmacc_vv_i32m2` 加宽累加。pack 与垂直逐位相同。

真机 K3：

| 场景 | C | RVV | 比值 |
|---|---|---|---|
| 内核：纯水平 1920×1080→1280×1080 | 25.689–25.880 ms | **9.606–9.643 ms** | **2.67×** |
| 整链 1920×1080→1280×720 | 40.861–41.113 ms | **9.639–9.653 ms** | **4.24×** |
| 整链 1280×720→1920×1080（上采样） | 45.908 ms | **10.421 ms** | **4.41×** |
| 整链 640×480→1280×720（小尺寸） | 20.168 ms | **4.565 ms** | **4.42×** |
| 只横向 1280×720→640×720 | 10.505 ms | **4.159 ms** | **2.53×** |

全部哈希与 C 侧逐字节一致（`fdbfc49578568fcf` / `3f41cccccde96e72` / `cb9a5e709d715894` /
`fa4a9830ee399d9c` / `a54a177550e00b32`）。**zimg 的整链从 2.02× 提到 4.24×，是目前所有包里最高。**

**一条必须记住的坑**：qemu 下这份 gather 实现是 **245.6 ms，比 C 的 32.5 ms 慢 7.5 倍**；
真机却是 9.64 ms，快 4.24 倍。索引装载在 qemu 里逐字节模拟，代价与真机完全不成比例——
如果拿 qemu 计时做取舍，这个正确且大幅收益的实现会被直接否掉。qemu 只判功能，性能只在真机取。

剩余：FLOAT 路径、`depth`（depth_convert/dither）、`colorspace`、运行时 CPU 探测。

### 4.11 libvpx SSE（内核 3.0–6.5× / 整链 1.131×）

SAD 收口后，同族还剩 `vpx_sse`（平方差和，RD 代价与模式选择高频）。它是通用宽高函数，
没有 rtcd 尺寸表要改，比 SAD 更好接。

内核三段：`vzext u8→u16`、相减得 i16 差（[-255,255]）、`vwmacc_vv_i32m4(d,d)` 加宽累加。

两个坑值得记：

1. **必须用有符号 vwmacc**。差会为负，先 `vreinterpret u16→i16` 再加宽乘；
   用无符号版会把 `0xFFxx` 当大正数，结果全错（qemu 逐值差分能抓到）。
2. **归约要批量化 + GCC 14.2 没有 u32 源的加宽归约**。第一版逐行 `vse32` 存栈求和，
   16×16 时开销等于 100%（16 乘加配 16 标量加）。改成 i32 车道跨行累加、每 30000 像素
   归约一次（30000×65025≈1.95e9<2³¹ 安全）。而 `vwredsumu_vs_u64m1_u32m2` /
   `vs_u64m2_u32m4` / `vredsumu_vs_u32m1_u32m4` 在 GCC 14.2 上全部 "implicit declaration"
   ——只有 u16 源的 `vwredsumu_vs_u16m2_u32m1`（SAD 在用）是存在的，u32 源没有。

真机 K3：

| 级别 | C | RVV | 比值 |
|---|---|---|---|
| 内核 16×16 | 403.3–405.1 ns | **134.7 ns** | **3.00×** |
| 内核 32×32 | 1252.4–1252.6 ns | **256.8 ns** | **4.88×** |
| 内核 64×64 | 6063.2–6087.7 ns | **932.1 ns** | **6.52×** |
| 整链 VP8 128×96/10 帧 | 574.77–576.10 ms | **508.23–509.15 ms** | **1.131×** |

哈希两侧完全一致（`fnv_bit=62a63640d7690a11` / `fnv_px=f85eaa8153b093fc`）。

**诚实结论**：内核 3–6.5× 很硬，整链只从 1.12× 抬到 1.131×。128×96 的编码主循环里
`vpx_sse` 的调用量远小于 SAD，其余（变换、量化、熵编码、RD 比较）还是 C。
这条路的上限不在内核效率，在"接了几个内核"——要继续抬得接 `vpx_variance*`、
`vpx_fdct/fht`、量化。

### 4.12 openssl Zvk 汇编（第八个自带向量实现的包）

openssl 停 G2 是因为"没碰向量"。查下来它**根本不需要我们写内核**：perlasm 层早就有

```
crypto/aes/asm/aes-riscv64-zvkned.pl / -zvkb-zvkned.pl / -zvbb-zvkg-zvkned.pl
crypto/sha/asm/sha256-riscv64-zvkb-zvknha_or_zvknhb.pl / sha512-...zvknhb.pl / *-zbb.pl
```

`crypto/aes/build.info` 的 `IF[$target{asm_arch} eq "riscv64"]` 无条件编入，运行时按 hwprobe 选择。

**这也暴露了普查方法的盲区**：`grep -rl "__riscv_v\|riscv_vector"` 只覆盖 intrinsics，
覆盖不到 perlasm。perlasm 类包（openssl / x264 / libvpx / ffmpeg）要先看 `*/asm/*riscv*`。

口径：两侧 C 代码同为 `-march=rv64gc`（无向量），唯一变量是 `no-asm`。真机 K3、64 KiB：

| 路径 | off | on | 比值 |
|---|---|---|---|
| AES-128-CBC enc | 7.03–7.07 ms | **0.051 ms** | **≈138×** |
| AES-128-CBC dec | 7.43 ms | **0.052 ms** | **≈143×** |
| AES-128-CTR | 7.10–7.12 ms | **0.025 ms** | **≈284×** |
| SHA-256 | 0.662–0.665 ms | **0.078 ms** | **8.5×** |
| **AES-256-GCM**（AAD 16B+IV 12B，续测） | 9.905–10.064 ms | **0.035 ms** | **≈287×** |
| **SHA-512**（续测） | 0.368–0.369 ms | **0.099 ms** | **≈3.7×** |

产物逐字节一致（`fnv_ct=cc18494f5e673a69`、`fnv_ctr=5c61394dab555006`、`sha256=b5c66c4d…`、
`fnv_gcm=277da5ef19ec13c4`、`tag=be1f5baad4e36232b20cd367555be2bf`、`sha512=b9e2c354…`）。

**GCM 的 287× 是两条 Zvk 扩展叠加**：`nm` 查到 `gcm_ghash_rv64i_zvkg` / `gcm_gmult_rv64i_zvkg`
（GHASH 走 Zvkg 的 `vgmul`）与 `libcrypto-lib-aes-gcm-riscv64-zvkb-zvkg-zvkned.o`
（AES 轮走 Zvkned），而 off 侧 GHASH 是逐块 128-bit 多项式乘法的纯 C。SHA-512 走
`sha512_block_data_order_zvkb_zvknhb`，3.7× 低于 SHA-256 的 8.5×——64 位机上的标量
SHA-512 本来就接近理论吞吐，向量化的相对空间更小。

归因三重证据：①`libcrypto.a` 里 43 个 zvk 符号、含 `aes-gcm-...zvkned.o`；②qemu（无 Zvkned、
有 Zbb）里 SHA-256 快 1.74× 而 CBC/CTR 不变 → Zvkned 只在真机执行；③同机 libgcrypt 的
Zvkned CTR 是 39.4×，量级同源。**没能拿到单扩展隔离**：`OPENSSL_riscvcap` 在 4.2-dev 上
只要被设置就整体退回保守路径（六种写法全试过）。

### 4.13 zlib-ng adler32：两档 LMUL 实测，判定无向量化收益

zlib-ng 的 adler32 RVV 内核此前是唯一负优化项（0.928×）。本轮做了加宽试验（`e8m1/u16m2/u32m4`
→ `e8m2/u16m4/u32m8`），三侧对照（off=C / old=原内核 / new=加宽版）功能全部逐字节一致
（`crc=2644adc5 fnv=3bb0c93b653afa83`），性能：

| 侧 | adler16M | ns/byte | 相对 C |
|---|---|---|---|
| off（纯 C） | 3.633–3.648 ms | 0.217 | 1.000× |
| old（`e8m1`） | 3.935–3.950 ms | 0.235 | **0.928×** |
| new（`e8m2`） | 4.309–4.324 ms | 0.257 | **0.843×** |

加宽反而更慢：`u32m8` 占 8 个向量寄存器，K3 只有 32 个 reg，`u16m4`+`u8m2` 同时活跃
直接触发 spill；指令条数减半但单指令代价涨得更多。**瓶颈不在 LMUL，而在"8 位数据要两次
`vwaddu` 加宽"这个形态**——标量 unrolled 版本靠 L1 带宽就能跑满。

屏蔽也评估过：只删派发表两行会撞 `init_functable()` 的 `FUNCTABLE_VERIFY_ASSIGN` 断言
（`ft` 是 `memset(0)`，未赋值即 NULL），必须同时处理 `ADLER32_FALLBACK`、
`RISCV_RVV_NATIVE`、`native_adler32` 宏映射三处，换整链约 2.4%，**判定不划算**，
保持上游默认。若换到 VLEN ≥ 512 的板子可用 `scripts/g3-adler-reeval.sh` 重测。

### 4.14 Eigen RVV10 后端：工具链打通 + 真机 A/B

卡点从来不是代码，是 `__riscv_v_fixed_vlen` 这个编译器契约：

| 编译器 | `-march=rv64gcv_zvl256b` | 加 `-mrvv-vector-bits=zvl` |
|---|---|---|
| GCC 13.3（镜像默认） | 只给 `__riscv_v_min_vlen 256` | **选项不认识** |
| GCC 14.2（`g++-14-riscv64-linux-gnu`） | 同上 | 认，给出 `__riscv_v_fixed_vlen 256` |
| GCC 15.2（真机 Bianbu 自带） | 同上 | 认，给出 `__riscv_v_fixed_vlen 256` |

即"`-mrvv-vector-bits` 是 Clang 专属"只对 GCC 13 成立。两侧唯一变量 `EIGEN_RISCV64_USE_RVV10`，
同编译器同 march，真机原生（GCC 15.2）5 轮 best-of-5，重复三轮：

| 用例 | off（标量 C++） | on（RVV10） | 加速 |
|---|---|---|---|
| `imatmul 64×64`（int32） | 0.646 ms | 0.068–0.069 ms | **9.4×** |
| `dmatmul 128×128`（double） | 13.459–13.474 ms | 0.765–0.767 ms | **17.6×** |

功能：`imatmul fnv=b6934bd0094dc25a mismatch=0/4096`、`dmatmul fnv=72dccc2fcdc7d3ba
max_rel=2.346e-13`，三轮全 `BYTES_SAME`。

**一条新教训**：容器 GCC 14 编出的 on 侧在 qemu（vlen=256）下 `imatmul` 哈希是
`70008b1ef18c9fc1`（与 off 不一致），搬到真机却完全相同。**qemu 对 RVV10 的多寄存器整数
kernel 模拟有缺陷**，它连功能都不能采信，只能当冒烟测试——配合 §4.9 的"qemu gather 慢 7.5 倍"，
可以定论：**qemu 只回答"能不能启动与跑到结束"，功能与性能都必须真机。**

### 4.15 crypto++ AES-256-CTR：Zvkned + 接管多块派发（3.15×）

**为什么值得做**：crypto++ 的 `Rijndael::Enc` 在 riscv 上没有 SIMD 分支，走的是
T-table 标量 C；而 K3 自带 `zvkned`，一条 `vaesem` 就能完成一整轮
（SubBytes+ShiftRows+MixColumns），一条 `vaesef` 完成末轮。

**指令面实测**（Bianbu binutils 2.46，`as`）：

| 助记符 | 可编 | 备注 |
|---|---|---|
| `vaesem.vv vd, vs2` | 是 | 中间轮 |
| `vaesef.vv vd, vs2` | 是 | 末轮（无 MixColumns） |
| `vaesefs.vv` / `vaesel.vv` / 3 操作数 / `.vs` | 否 | 全 FAIL |

`riscv_crypto.h`（gcc 15，309 行）无 vaes intrinsic，只能内联汇编。

**语义不猜，用零基准单轮对拍**：`in[i]=i*17+3`、`key[i]=i+1`，
`vaesem` 输出 `ab7eba9883fc2f86ae75dc3a40d57fd1`、`vaesef` 输出
`7a689673a5d8a60d34eb34d687f4f6be`，与 Python 独立实现的
SubBytes+ShiftRows(+MixColumns)+AddKey 逐字节一致 ⇒ **状态在 vd（兼目标），轮密钥在 vs2**。

**最难的一坑**：`UncheckedSetKey` 只对**首轮与末轮**做
`ConditionalByteReverse(BIG_ENDIAN_ORDER, ...)`，中间轮保持大端 word。于是
`k[0]`、`k[R]` 直接 `vle32`，`k[1..R-1]` 才要 `vrev8`。对全体都做 `vrev8`
的表现是"性能已 3× 但哈希不符、且输出不落在任何中间轮上"。

**六条路径一起测**（64 KiB，5 轮 × best-of-5，三轮重复）：

| 路径 | off（T-table C） | on（Zvkned） | 倍率 |
|---|---|---|---|
| AES-256 CTR | 0.953 / 0.978 / 0.953 ms | **0.302 ms** | **3.15×** |
| AES-256 CBC | 0.982 / 1.010 / 0.982 | **0.313 ms** | **3.14×** |
| AES-192 CTR | 0.843 / 0.865 / 0.843 | **0.264 ms** | **3.19×** |
| AES-192 CBC | 0.872 / 0.895 / 0.872 | **0.275 ms** | **3.17×** |
| AES-128 CTR | 0.734 / 0.756 / 0.734 | **0.226 ms** | **3.25×** |
| AES-128 CBC | 0.763 / 0.787 / 0.763 | **0.237 ms** | **3.22×** |

**受控实验推翻了"派发层是瓶颈"这个推断**：把多块接管临时禁用（`if (0)` 替掉分派条件重编库），
同一份负载测得单块 0.302/0.310 ms、多块 0.302/0.311 ms——**两者完全等价**。
K3 的乱序执行把每块 15 次 `vle32+vrev8` 吸收进了 `vaesem` 的延迟里。3.15× 全部归因于
**Zvkned 把一整轮压成一条指令**，与派发粒度无关。

早期一次"AES-256 单块只有 1.026×"的记录**作废**：那次 on/off 仅差 2.6%，与受控实验不一致，
取到了不可靠的中间态库。这也是本轮唯一一条被自己推翻的结论，留在这里作为口径提醒——
**性能结论必须有同轮受控对照，跨轮比较不可引用**。

**功能**：三轮 A/B 哈希 `aesctr fnv=6b642726bef75efc`、`sha256 fnv=ab0624b961d45259`
两侧全同，`cmp` 得 `BYTES_SAME`；SHA-256 两侧 0.776–0.821 ms 无变化，反证 A/B 只有一个变量。

**边界**：只接管 `m_rounds == 14` 且 flags 恰为 `BT_InBlockIsCounter` 的纯 CTR；
AES-128/192、CBC/XTS/`BT_XorInput` 一律回落基类 T-table 路径，不改变任何语义。

**验证的中间产物**（都在板上）：`vt.c`（纯 asm 单轮语义对拍）、`vt2.c`（intrinsic+vrev8 单轮）、
`vt3.c`（用 60 个 round-key 常量做 14 轮，输出 `8c5b77dfa6593649d2620ad83c244a88` 与 off 一致）、
`k1.cpp`（单块 + 3 块 CTR 小样本）。
