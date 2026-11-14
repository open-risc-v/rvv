# G3 内核阶段：队列、口径与真机 A/B

G2 只证明"交叉编译能跑、输出一致"。G3 要回答的是**换个向量实现，结果是否还一致、真机上快多少**。

## 1. 先分类：哪些包需要"写"，哪些只需要"打开"

对 17 个已拉源码的包做了一次 SIMD 实现普查（`grep -rl` 统计，单位=文件数）：

| 包 | SSE 文件 | NEON 文件 | 上游已有 RVV | G3 策略 |
|---|---|---|---|---|
| libaom | 283 | 264 | 13 | 打开上游 RVV + 验收 |
| libvpx | 196 | 178 | 0 | 写内核（SSE/NEON 数量最大，优先级最高的长尾） |
| fftw | 88 | 74 | 0 | 写内核（codelet 结构特殊，先做 dft 1d 的复乘/蝶形） |
| cryptopp | 79 | 61 | 0 | 打开上游 RISC-V 后端的可用部分，缺的补 |
| libjpeg-turbo | 70 | 19 | 12 | 打开上游 RVV + 验收（已有 IDCT/颜色转换） |
| openh264 | 64 | 96 | 0 | 写内核（先用 deblock/IDCT） |
| gromacs | 61 | 28 | 1 | 写内核（非 bonding 力计算的 gather 型循环） |
| zlib-ng | 47 | 31 | 6 | 打开上游 RVV + 补缺失的 adler/crc 路径 |
| libwebp | 45 | 40 | 0 | 写内核（YUV→RGB、fancy upsampling） |
| webrtc-ap | 45 | 52 | 0 | 写内核（先 resampler） |
| opus | 44 | 62 | 0 | 写内核（先 NSQ / celt 的 pitch 后处理） |
| botan | 35 | 26 | 0 | 打开上游 RISC-V 后端（若有）否则写 AES/CTR |
| openssl | 32 | 31 | 0 | 用 rv64gcv 的 asm 后端，缺的补 |
| x264 | 24 | 19 | 0 | 写内核（先 SATD/SAD） |
| zimg | 17 | 20 | 0 | 写内核（先 resize 的水平卷积） |
| pixman | 12 | 12 | 2（`pixman-rvv.c`，约 1500 行） | **打开 + 验收**（已完成，见下） |
| libgcrypt | 11 | 36 | 13 | 打开上游 RVV + 验收 |
| libde265 | 9 | 8 | 0 | 写内核（先 IDCT/变换） |

结论：**8 个包上游已经有 RVV 实现**（pixman/libjpeg-turbo/libgcrypt/zlib-ng/libaom/eigen/libpng/gromacs 各有一点），
它们的 G3 首先应该"打开并对齐口径"，而不是从零写；剩下 9 个才需要真写内核。

## 2. A/B 口径（所有包统一）

| 侧 | 配置 |
|---|---|
| A | `-march=rv64gcv`（必要时 `rv64gcv_zba_zbb_zbc_zbs_zicond`），启用该包自己的向量路径 |
| B | **同一 march**，关掉向量路径（`USE_RVV` / `rvv=disabled` / `RVV_KERNELS=OFF`） |

只允许一个变量。若 B 侧降 march（如 `rv64gc`），比出来的是"向量 vs 完全没有向量"，
不能说明手写内核相对编译器自动向量化的增益——那正是 G3 要判断的东西。

功能门禁：qemu 下逐字节一致（浮点内核按相对误差 ≤1e-6 判）。
性能门禁：**只在真机上取**，每个二进制至少 5 次、取中位数，两个二进制交替跑（避免热降频偏袒）。

## 3. 真机 A/B 的执行路径

```bash
# 1) 交叉编出 A/B 两个前缀 + 静态基准二进制（容器内，产物在 build/rvv-k/{on,off}）
~/work/<pkg>-rvv/scripts/rvv-kernel-ab.sh

# 2) 推到板上跑，打印 A/B 与加速比
~/work/rvv/scripts/board-ab.sh <pkg> <board-host>
```

前提：板上 CPU 支持 RVV 1.0（`vlen >= 128`），能执行静态 riscv64 二进制，SSH 可达。

## 4. 进展

| 包 | G3 状态 | 结果 |
|---|---|---|
| pixman | 功能已验收 | 上游 RVV 路径打开，与 `rvv=disabled` 逐字节一致（`fnv=066ba22180589ab5`）；性能待真机 |
