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

## 3. 性能结果：缺真机，未填

G3 的性能门禁规定只能上真机。当前环境里没有可达的 RISC-V 板（机器上没有任何能连到
riscv 主机的 ssh 配置），因此性能列为空，**不拿 qemu 数字充数**。

每个包都已产出可直接上板的静态二进制与驱动：

```bash
# 板上执行（自动完成 环境探测 → 推包 → A/B 交替跑 → 加速比）
~/work/rvv/scripts/board-ab.sh pixman  <board-host>
~/work/rvv/scripts/board-ab.sh zlib-ng <board-host>
```

待补的数据（每包 3 行）：板上 `uname -a` 与 `isa`（确认 RVV 1.0 与 VLEN）、
A/B 各自的 `ns_per_px` 或 `*_ms`、加速比。

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
| eigen | 2 个（部分 packet math），待做 |
| gromacs | 1 个（很局部），主体仍需写 |

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
11. **botan / openssl**（AES/CTR，openssl 优先用 rv64gcv asm 后端）

## 5. 本轮顺带修掉的通用坑

`test/cpu_probe.c` 的 `vrgather` 微基准用有符号向量做索引，GCC 14 起
`__riscv_vrgather_vv_i32m2` 只接受 `vuint32m2_t`，RVV 目标下直接编不过。
已批量修掉 **20 个工程**的副本，并同步修进 Skill 模板 `assets/skeleton/test/cpu_probe.c`，
以后新建工程不会再带这个 bug。
