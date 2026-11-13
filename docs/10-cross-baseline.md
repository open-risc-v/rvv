# 交叉编译基线（G3 的前置门禁）

native 上的 A/B 只回答"上游能编、真实调用路径能跑、门禁通道可靠"。它**不回答**"这份上游
在 riscv64 上能不能编、能不能跑、输出是否与 native 一致"。后者是交叉基线要证明的事，
也是任何 RVV 内核开工前的必要条件——没有它，内核失配时分不清是内核写错还是交叉链路搭错。

## 1. 口径

| 项 | 值 |
|---|---|
| 镜像 | `rvv-cross:1/2`（Ubuntu 24.04 + riscv gcc/g++ 13.3 + qemu + cmake/ninja/meson/autotools）；native 侧用 `rvv-build:1/2`（+ zlib1g-dev、gpg-error 1.61） |
| 编译位置 | **一律在 Linux 容器内，宿主（macOS）只当编辑器**。native A/B 走各工程 `./scripts/native-baseline.sh` |
| 编译器 | `riscv64-linux-gnu-gcc 13.3`（Ubuntu 24.04） |
| sysroot | `/usr/riscv64-linux-gnu` |
| 执行 | `qemu-riscv64 -L /usr/riscv64-linux-gnu`（**功能判定，不是性能**） |
| 基线 march | `-march=rv64gc`（无向量）。向量留给内核阶段：`MARCH=rv64gcv` |
| 落盘 | 各工程 `build/riscv64-b/{bld,prefix,harness,out}` |

每条工程一条命令：`./scripts/cross-baseline.sh`（骨架已自带，CMake 上游开箱可用）。

## 2. 六项结果

| 工程 | 上游构建系统 | riscv64 输出 | native 输出 | 判定 |
|---|---|---|---|---|
| zlib-ng-rvv | CMake（`ZLIB_COMPAT=ON`） | `in=200003 out=73562 crc=2644adc5 fnv=3bb0c93b653afa83` | 同左 | 一致（压缩字节也一致） |
| libjpeg-turbo-rvv | CMake（`WITH_SIMD=ON`） | `size=128x96 jpeg=2799 fnv_jpeg=f0dd2e9ada7876e4 fnv_px=79887ab513b04ba1` | 同左 | 一致（JPEG 字节也一致） |
| pixman-rvv | meson（`--cross-file`） | `size=129x97 fnv=066ba22180589ab5` | 同左 | 一致（PPM 字节也一致） |
| libpng-rvv | CMake（`PNG_TESTS=OFF`） | `size=131x99 png=28995 fnv_png=3bd158cd… fnv_px=7322844870c2c46b` | 同左（`png=28995 fnv_png=3bd158cd…`） | 一致（码流与像素都一致） |
| openssl-rvv | `perl Configure linux64-riscv64` | `sha256=b5c66c… fnv_ct=cc18494f5e673a69` | 同左 | 一致（密文与摘要都一致） |
| libgcrypt-rvv | autotools（`autoreconf -fi`） | `n=65536 ver=1.12.5-unknown sha256=8ae5324f… fnv_ct=1b61c683d7e61c03` | 同左 | 一致（摘要与密文都一致） |

### libpng 的 zlib 提供方必须两侧一致

libpng 的输出字节直接由 zlib 决定，所以**两侧必须用同一个 zlib 实现**才谈得上逐字节。
之前 native 走宿主系统 zlib、riscv 走 `zlib-ng` 前缀，压缩字节不同（28936 vs 28995），
只有像素哈希一致；这是"zlib 不同"，不是移植引入的差异。
现在 `libpng-rvv/scripts/native-baseline.sh` 也挂 `../zlib-ng-rvv` 的 native 前缀，
两侧同为 zlib-ng（ZLIB_COMPAT）⇒ `png=28995 fnv_png=3bd158cd…` 与 riscv 侧完全相同。
判据回到"逐字节一致"，不再需要"像素一致"这种降级口径。

## 3. 这一轮证明了什么、没证明什么

证明：

- 六类构建系统（cmake / meson / autotools / perl Configure）都能被这套 riscv 工具链编过去；
- 交叉产物在 qemu 里真的跑通，且**输出与 native 逐字段一致**；
- 探针与用例是架构无关的：同一份 `test/pkg_*.c` 两边都能编、都能给出可比哈希。

没证明：

- **没有任何加速**。此刻 `src/` 与 `baseline/` 内容相同，`RVV_KERNELS` 关闭，
  `rv64gc` 不含向量指令，两侧机器码等价。
- 没有性能数字。qemu-user 的耗时不能当性能结论，G3 的真机数据来自 `benchmark/pair_bench.sh`。

## 4. libgcrypt：已解除（2026-11-13 晚）

**结论**：不是架构问题，是依赖版本问题；用官方 tar 直接交叉编 1.61 就好了。

libgcrypt master 的 `configure` 要求 `libgpg-error >= 1.56`：

```
checking for GPG Error - version >= 1.56... no
configure: error: libgpg-error is needed.
```

容器（Ubuntu 24.04）只有 `libgpg-error 1.47`。之前的失败是走 `apt-get source` 卡在
debian sid 索引（不产出任何文件），不是网络不通——**直接下载 gnupg.org 官方 tar 即可**：

```bash
curl -LO https://gnupg.org/ftp/gcrypt/libgpg-error/libgpg-error-1.61.tar.bz2     # 1.1 MB，秒下
# Dockerfile：FROM rvv-cross:1 → configure --host=riscv64-linux-gnu --prefix=/opt/gpg-error
docker build -t rvv-cross-gperr:3 .
```

两个真实坑（都已修进镜像/脚本）：

| 坑 | 现象 | 处理 |
|---|---|---|
| 1.61 不再安装 `gpg-error-config` | `checking for GPG Error - version >= 1.56... no`，且 `/opt/gpg-error/bin/gpg-error-config: No such file` | 镜像里加 shim：`--version/--cflags/--libs/--host` 走固定值，其余转给 `gpgrt-config` |
| libgcrypt 的 `tests/` 不吃 `GPG_ERROR_CFLAGS` | `tests/t-lock.c: fatal error: gpg-error.h: No such file` | configure 传 `CPPFLAGS=-I/opt/gpg-error/include` |

结果：`rvv-cross-gperr:3` 里 `libgpg-error.a` 是 **riscv64** 静态库（1.61），
`libgcrypt` 交叉后探针输出与 native 逐字段一致（见 §2）。

## 5. 对计划的影响

交叉基线不改变波次与工期：它是每项 G2→G3 之间的固定一步（约 0.3–0.5 人日/包，
已含在 D2/D3 的验证工时里）。它带来的收益是**把 G3 的失败面收窄**：
内核上线后若哈希变，只可能是内核逻辑，不会是工具链或 sysroot。

## 6. 复现

```bash
# 单项（native 在容器内跑 A/B，交叉在容器内跑 riscv64 + qemu）
cd ~/work/zlib-ng-rvv && ./scripts/native-baseline.sh && ./scripts/cross-baseline.sh

# 想看向量路径（上游自带 RVV 代码时）
MARCH=rv64gcv ./scripts/cross-baseline.sh

# 镜像不在时
docker run --rm rvv-cross:1 riscv64-linux-gnu-gcc --version
```
