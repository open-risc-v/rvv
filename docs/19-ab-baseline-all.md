# 全量交叉编译 A/B 基线汇总（rv64gc）

口径：同一份上游、同一组编译选项，两侧只差目标 ISA（`riscv64-linux-gnu-gcc -march=rv64gc`
对 native `gcc/g++`），riscv 侧用 `qemu-riscv64 -L /usr/riscv64-linux-gnu` 执行。
**qemu 只判功能，不出性能**。全部在 Linux 云主机（env_id=vm）上编译，macOS 不参与编译。

- 驱动脚本：`scripts/local-cross.sh <pkg>-rvv`，一条命令跑完「交叉编上游 → 编/跑探针 → native 对照 → 比对」。
- 每包产物：`projects/<pkg>-rvv/build/{riscv64-b,native}/{prefix,harness,out}`，判定行同时写入 `out/ab-result.txt`。
- 判据分三档：① 输出哈希逐位一致；② 解码像素一致（码流允许因压缩实现不同而不同）；③ 浮点/自适应滤波包按相对容差，并额外比 8bit 量化哈希。

| # | 工程 | 上游构建系统 | 关键实测输出（riscv64） | 判定 |
|---|---|---|---|---|
| 1 | zlib-ng-rvv | cmake | `in=200003 out=73562 crc=2644adc5 fnv=3bb0c93b653afa83` | 逐位一致（压缩字节也一致） |
| 2 | libpng-rvv | cmake | `size=131x99 png=28995 fnv_px=7322844870c2c46b` | 像素一致（native 码流 28936 字节，压缩实现不同） |
| 3 | libjpeg-turbo-rvv | cmake | `size=128x96 jpeg=2799 fnv_jpeg=f0dd2e9ada7876e4 fnv_px=79887ab513b04ba1` | 逐位一致（JPEG 字节也一致） |
| 4 | libde265-rvv | cmake | `dec frames=10 bytes=61440 fnv_px=cf67fb9981835c6a` | 像素一致 |
| 5 | libwebp-rvv | cmake | `lossless=30026 fnv_ll=69c27e48073e9609 px_diff=0 lossy=4706` | 像素一致（lossless 码流也一致） |
| 6 | opus-rvv | autotools | `frames=120 bytes=19200 fnv_bit=a04caa33e5671901 fnv_pcm=74bc2325f58a2e04` | 逐位一致 |
| 7 | pixman-rvv | meson | `size=129x97 fnv=066ba22180589ab5` | 逐位一致 |
| 8 | zimg-rvv | meson | `resize 96x72 fnv=63a1b96d955d6536；depth fnv=1ca7dee4e96750f5` | 逐位一致 |
| 9 | nettle-rvv | autotools | 两个摘要文件逐字节一致 | 逐位一致 |
| 10 | libspeex-rvv | autotools | nb/wb/uwb × q2/q8 六用例全 PASS | 逐位一致 |
| 11 | speexdsp-rvv | autotools | `frames=200 fnv_out=d5e90ea7fe76fa33`（`--enable-fixed-point`） | 逐位一致 |
| 12 | flac-rvv | autotools | `samples=4096 flac=5567 fnv_stream=3ee0eaec79e78bfd fnv_pcm=75f1bdc1ebc3575b` | 逐位一致 |
| 13 | libvpx-rvv | autotools | `frames=10 bytes=10766 fnv_bit=62a63640d7690a11 dec fnv_px=f85eaa8153b093fc` | 像素一致 |
| 14 | x264-rvv | autotools | `enc frames=10 bytes=690 fnv_bit=91e876b2b8b16d8c` | 逐位一致（日志噪声不影响判定） |
| 15 | openh264-rvv | make | `frames=10 bytes=8619 fnv_bit=316f1b141efb69a7 dec fnv_px=762b92ca7ae625a5` | 逐位一致（ARCH 无 riscv，走纯 C） |
| 16 | openssl-rvv | perl Configure | `sha256=b5c66c4d… fnv_ct=cc18494f5e673a69 fnv_gcm=277da5ef19ec13c4` | 逐位一致 |
| 17 | cryptopp-rvv | make | `sha256 fnv=ab0624b961d45259 aes256ctr=6b642726bef75efc aes256cbc=889fb3dcc628ed12` | 逐位一致 |
| 18 | botan-rvv | configure.py | `sha256 fnv=ab0624b961d45259 aesctr n=65536 fnv=6b642726bef75efc` | 逐位一致 |
| 19 | eigen-rvv | header-only | `imatmul 64x64 fnv=b6934bd0094dc25a mismatch=0/4096` | 逐位一致 |
| 20 | stockfish-rvv | make | `info depth 18 nodes 200176 … bestmove b5a4 ponder g8f6` | 逐位一致（UCI 直跑，非探针） |
| 21 | libgcrypt-rvv | autotools | `n=65536 ver=1.12.5 sha256=8ae5324f… fnv_ct=1b61c683d7e61c03` | 逐位一致（依赖交叉 libgpg-error 1.62） |
| 22 | fftw-rvv | autotools（官方发布包） | `dft1024 max_rel=3.112e-14 fnv=7c2af68f8fe41f90` | 容差 1e-6 内一致（浮点包不比逐字节） |
| 23 | webrtc-ap-rvv | meson | `frames=200 pcm=96000 energy=8714.207510`（native 8714.209828，相对差 3e-7） | 容差 1e-5 内一致（自适应滤波器逐字节不可达） |
| 24 | mpg123-rvv | autotools（官方发布包） | `decoded=176400 fnv_q8=d9d5b2bd265e8b8b` | 8bit 量化哈希逐位一致（原件哈希因浮点末位不同） |
| 25 | libaom-rvv | cmake（官方发布包） | `frames=5 bytes=2380 fnv_bit=240a4878e6072e89 fnv_px=714f34de78d4e4d6` | 逐位一致（码流与像素都一致） |
| 26 | gromacs-rvv | cmake | `gmx editconf -box 5 5 5 -c` 输出结构文件 | 待填 |

排除项（按用户指示不立项）：`sci-libs/gdal`、`sys-cluster/ceph`。

## 上游参照变更（有据可查）

| 包 | 原参照 | 现参照 | 原因 |
|---|---|---|---|
| fftw | `github.com/FFTW/fftw3` @ `a7b679c` | `https://fftw.org/fftw-3.3.10.tar.gz` | git 源码不含 codelet，需 OCaml genfft 生成；构建期报 `No rule to make target 'n1_2.c'` |
| libaom | `aomedia.googlesource.com/aom` @ `8669fa8` | `aom_3.3.0.orig.tar.gz`（archive.ubuntu.com） | googlesource 在本机网络完全不可达（curl 无响应） |
| mpg123 | `mpg123.org` tarball | 同左 | 仅补了 fetch 脚本的 tarball 分支 |

两处变更都写在各自 `project.conf` 的 `UPSTREAM_NOTE` 里，A/B 两侧仍用同一份源码，参照一致性不受影响；但**跨轮次比较基线版本时必须知道这两处换过参照**。

## 工具链与前置

- `riscv64-linux-gnu-gcc/g++ 11.4.0`、`qemu-riscv64 6.2`（apt，仅 rv64gc）、`cmake 3.22`（gromacs 需 4.x，用 `pip install --user cmake` 得到的 4.4.5）、`meson`、`autotools`、`nasm 2.15.05`。
- 交叉外部前缀：`/opt/gpg-riscv`（libgpg-error 1.62 riscv）、`/opt/gpg-native`（同版本 x86_64）。**注意**：`libgpg-error` 的 `.a` 必须是 riscv 目标文件，之前 `./autogen.sh` 冲掉交叉配置导致归档里全是 x86 目标文件（`file` 可验证）。
- `/opt/qemu82`（qemu 8.2.7，支持 RVV 1.0）未重建，`MARCH=rv64gcv` 验证目前只能靠 qemu 6.2，会报 Illegal instruction；**向量验证需等重建或上真机**。
