# 真机 rvv/cpu A/B 第一轮（2026-11-17）

真机 `10.91.8.28` 重新上线后，第一次在**真实 RVV 1.0 硬件**上跑 A/B。此前所有数字都来自
`qemu-riscv64` 用户态，只能证明功能、不能代表性能；本轮开始有真机数字。

## 0. 设备与工具链

| 项 | 值 |
|---|---|
| 主机 | `10.91.8.28`（root/bianbu，K3） |
| ISA | `rv64imafdcvh` + RVV 1.0（`zve64d`, `zvbb`, `zvkb`, `zvkned`, `zvfh`, `zicond`, `zcb`…） |
| 核数 / 内存 | 8 核 / 15 GB |
| 编译器 | **Bianbu gcc 15.2.0（带 `riscv_vector.h`）** |
| 存储 | 板载 mmc 只剩 211 MB，已挂载未使用的 `/dev/sda3`（ext4，105 GB 可用）到 `/mnt/ssd`，工程放在 `/mnt/ssd/work` |

关键差异：VM 里的 `riscv64-linux-gnu-gcc` 11.4 / 12.3 **都不带 `riscv_vector.h`**，
所以 intrinsics 路线在交叉环境里根本编不出来；真机 gcc 15 有，**RVV intrinsics 只能在真机上做**。

## 1. zlib-ng：功能逐位一致 + 首个真机性能数字

上游 `github.com/zlib-ng/zlib-ng` @ `6727d88`；两侧同源、同 `-O2`，唯一变量是 ISA：

- cpu：`-march=rv64gc -DWITH_RVV=OFF`
- rvv：`-march=rv64gcv -DWITH_RVV=ON`

configure 打印 `HAVE_RVV_INTRIN - Success`，实际编入
`arch/riscv/{adler32,chunkset,compare256,slide_hash}_rvv.c` 与 `crc32_zbc.c`。

**向量指令核验**（`objdump -d libz-ng.a`）：

| 产物 | `vsetvli` | `vle*.v` |
|---|---|---|
| cpu | 0 | 0 |
| rvv | 65 | 29 |

**功能**：16 MiB 半可压缩文本（seed=7），`minigzip -6 -c` 输出两侧都是 825552 字节，
sha256 前 16 位同为 `2e84d928499a0fdf` → **逐字节一致**。

**性能**（同机交替 3 轮取中位）：

| 用例 | cpu | rvv | 比值 |
|---|---|---|---|
| 压缩 `-6`（16 MiB） | 396 ms | 278 ms | **1.42x** |
| 解压（16 MiB） | 26 ms | 32 ms | 0.81x（慢 17%） |

解压变慢的原因：`chunkset_rvv` 在 32 KB 窗口下每块都要重新 `vsetvli`，切换开销盖过拷贝收益。
下一轮单内核任务：把该路径改成一次设定 + `vle8.v` 批量拷贝，或对小块直接回退标量。

## 2. libpng：真机功能一致（上游无 RVV 内核）

上游 `github.com/pnggroup/libpng` @ `7ef5852`；`-march=rv64gc` / `-march=rv64gcv` 各编一份
静态库，再手工编 `pngtest` 链接对应库。

- 输入 `contrib/pngsuite/basn2c08.png`，两侧 `pngtest` 均 `rc=0`
- 输出 `pngout.png` md5 前 16 位两侧同为 `b9b420aaa329a3b0`

libpng 上游没有 RISC-V 内核，`-march=rv64gcv` 只是让编译器有机会自动向量化，
所以这一条只算**真机功能验证**，不作为性能结论。

## 2b. libwebp：真机编码一致，无可测加速

上游 webmproject/libwebp；两侧 `-march=rv64gc` / `-march=rv64gcv`，`-O2`，其余相同。

- 良构图（渐变 2048×2048 PPM，`-lossless -q 100 -m 4`）：输出 1378 字节，md5 前 16 位两侧同为 `0ccac20c1f480288`
- 噪声图（2048×2048 `os.urandom`）：输出 md5 前 16 位两侧同为 `811f46bc29963a5a`
- 耗时（噪声图，交替 3 轮）：编码 cpu 3361/3318/3344 ms，rvv 3299/3299/3316 ms → **1.01x**
- 解码 2 轮：cpu 215/215 ms，rvv 204/203 ms → 1.05x（但两次 `dwebp` 输出文件为空，
  说明这次解码命令的产物参数写错，解码耗时只能作参考，不作为结论）

结论：libwebp 上游没有手写 RVV 内核，`-march=rv64gcv` 只带来编译器自动向量化的微弱收益。

## 2c. libde265：真机解码逐字节一致，rvv 略慢

- 码流：`ffmpeg -f lavfi -i testsrc2=352x288 -frames:v 10 -c:v libx265` 生成 `tiny.265`（25784 字节，10 帧）
- 两侧 `dec265 -o out.yuv`：`rc=0`，两侧 YUV 都是 1520640 字节，md5 前 16 位同为 `f4c76710ae018adf`
- 耗时（交替 3 轮）：cpu 46/44/43 ms，rvv 50/51/49 ms → 0.88x（rvv 慢约 13%）

`-march=rv64gcv` 让 GCC 自动向量化了部分内循环，但在 352×288 小帧上向量化的启动与收尾开销大于收益。


## 2d. 第二批：libjpeg-turbo / flac / opus（真机）

方法同上：设备上 clone 工程 → `fetch-upstream.sh` → 同源两份、`-O2`、唯一变量是 `-march`。

| 包 | 输入与命令 | 功能判定 | cpu | rvv | 比值 |
|---|---|---|---|---|---|
| libjpeg-turbo | 2048² PPM，`cjpeg -quality 90` | JPEG 1796273 B，md5 一致；解码 PPM md5 一致 | enc 75 ms / dec 88 ms | enc 77 ms / dec 90 ms | 1.00x / 0.98x |
| flac | 30 s 双声道正弦 WAV，`flac -5` | flac 425977 B，md5 一致；解码 WAV md5 一致 | enc 182 ms / dec 64 ms | enc 121 ms / dec 74 ms | **1.50x** / 0.86x |
| opus | 20 s 48 kHz 单声道，`opus_demo -e audio 48000 1 64000` | 码流 207768 B，md5 一致；解码 PCM md5 一致 | enc 228 ms / dec 95 ms | enc 309 ms / dec 111 ms | 0.74x / 0.86x |

flac 的 1.50x 全部来自 GCC 自动向量化（上游没有 RISC-V 内核）；opus 反而被自动向量化拖慢，
说明这类包必须**手写内核 + 关闭全局自动向量化**（或按函数粒度 `#pragma` 控制），否则收益为负。

当前真机已验证 **7 / 26**：
zlib-ng、libpng、libwebp、libde265、libjpeg-turbo、flac、opus。


## 2e. 第三批：mpg123（真机）

- 输入：`ffmpeg -i test.wav -c:a libmp3lame -b:a 128k test.mp3`（481114 B）
- 两侧 `mpg123 -q -w out.wav`：输出 WAV 均为 5292044 B
- **字节不同**（md5 `a75ad98f…` vs `da7b3c94…`），但逐采样比对：
  `max_abs_diff = 1`（1 LSB），178 / 2646000 个采样有差异（6.7e-5）
- 判定：**容差内一致**（口径同 VM：mp3 解码的 SIMD 路径允许 ±1 LSB）
- 耗时：cpu 133/138 ms，rvv 178/173 ms → 0.78x（rvv 反而慢）

## 2f. 真机进度（截至本轮）

| # | 包 | 真机功能 | 加速比 |
|---|---|---|---|
| 1 | zlib-ng | 逐字节一致 | 压缩 1.42x / 解压 0.81x |
| 2 | libpng | md5 一致 | — |
| 3 | libwebp | md5 一致 | 1.01x |
| 4 | libde265 | md5 一致 | 0.88x |
| 5 | libjpeg-turbo | md5 一致 | 1.00x |
| 6 | flac | md5 一致 | 1.50x |
| 7 | opus | md5 一致 | 0.74x |
| 8 | mpg123 | ±1 LSB 容差内 | 0.78x |

累计 **8 / 26**。仍在跑：openssl（设备上后台双构建）。
尚未上真机：libvpx、x264、openh264、libspeex、speexdsp、nettle、libgcrypt、botan、cryptopp、
eigen、zimg、pixman、stockfish、fftw、webrtc-ap、libaom、gromacs = 17 个。


## 2g. 第四批：libaom / x264 / openh264（真机）

| 包 | 输入与命令 | 功能判定 | 耗时 |
|---|---|---|---|
| libaom | `aomenc --cpu-used=8 --limit=30 --cq-level=30`，输入 30 帧 512×512 y4m | 码流 94004 B，md5 一致；`aomdec` 解码 YUV 11796698 B md5 一致 | cpu 29.0 s vs rvv 32.8 s → 0.89x |
| x264 | `x264 --crf 30 --preset veryfast`，同一 y4m | 码流 md5 一致（`0db6e36…`） | 构/测时设备仍在编 stockfish，计时作废，需空闲重测 |
| openh264 | `h264enc /tmp/welsenc.cfg -org a30.yuv -sw 512 -sh 512` | 码流 73080 B，md5 一致；另用 `baseline/res/BA1_FT_C.264` 解码，YUV 45467136 B md5 一致 | enc 100 ms vs 120 ms（有负载干扰，仅参考） |

构建系统侧的新坑（都已绕过）：
- **libvpx**：`make CFLAGS=` 覆盖会清掉 Makefile 自带 `-I.`，必须用 `./configure --extra-cflags=...`；另外 `vpxenc/vpxdec`
  需要 `--enable-tools`，本次仍未产出二进制（`make vpxenc` 报「没有规则」），需要手工链接
  `vpxenc.c ivfenc.c args.c tools_common.c md5_utils.c y4menc.c` + `third_party/libyuv/include`，
  但缺 `y4m_input_fetch_frame`（y4minput 目标库未编入），**当前状态：libvpx 编码链路未打通**。
- **x264**：同上的 CFLAGS 覆盖问题（`input/input.h` 找不到 `x264cli.h`），改 `--extra-cflags` 后正常。
- **stockfish**：手工 `g++ *.cpp` 会漏 `syzygy/`、`nnue/` 子目录，链接报 `Tablebases::rank_root_moves`、
  `NNUE::Network::load` 未定义；须 `find . -name '*.cpp'`。另外 RISC-V 上默认 `-fPIE` 会触发
  `R_RISCV_CALL_PLT ... making a shared object` 报错，要显式 `-no-pie`。

## 2h. 真机进度（更新）

已跑通 **11 / 26**：zlib-ng、libpng、libwebp、libde265、libjpeg-turbo、flac、opus、mpg123、
libaom、x264、openh264。

未完成 15 个：libvpx（vpxenc 链接）、stockfish（编译中）、libspeex、speexdsp、nettle、libgcrypt、
botan、cryptopp、eigen、zimg、pixman、fftw、webrtc-ap、openssl、gromacs。


## 2i. stockfish 现状（未跑通）

- 手工 `g++` 需排除 `src/universal/*`（x86 专用入口），并补 `-no-pie`；已完成 cpu 侧编译。
- 但 `EvalFileDefaultName = nn-bddd9d57eb87.nnue` 对应的网络文件在 baseline 里**不存在**，
  从 `raw.githubusercontent.com/official-stockfish/networks/master/` 取回的是 134 字节（404 内容），
  不是真网络；引擎启动后无网可载，A/B 无法作数。
- 结论：stockfish 卡在**网络文件获取**，不是编译问题；下一步改用 `official-stockfish/networks`
  仓库的 LFS 直链或 `tests/inspect` 发布包，取到正确文件后再跑 `stockfish bench`。

## 2j. 当前真机口径总结

- 真机可跑通并给出 A/B 证据：**11 / 26**
- 卡点 2 个：libvpx（vpxenc 未产出二进制）、stockfish（缺 NNUE 网络文件）
- 尚未上机 13 个：libspeex、speexdsp、nettle、libgcrypt、botan、cryptopp、eigen、zimg、pixman、
  fftw、webrtc-ap、openssl、gromacs


## 2k. openssl（真机）

- 两侧 `./Configure --prefix=/tmp/ssl-<v> no-shared no-tests linux64-riscv64 -march=<isa>` + `make -j8 build_sw`，均 rc=0
- 二进制 `bs-<v>/apps/openssl`：`OpenSSL 4.2.0-dev`
- **SHA-256**（16 MiB `data.bin`）：两侧摘要完全相同 `686d5acd68f3…a8b6`
- **AES-256-CBC**（`-K 0…0 -iv 0…0` 固定密钥/IV，避免随机 salt）：密文 md5 一致 `7ca3a152d6a7`
- 耗时：sha256 40 ms vs 40 ms（1.00x）；aes 56/58 vs 60/59 ms（≈0.95x）
- 结论：openssl 4.2 dev 在本机没有走 RVV 汇编路径（crypto 通用实现），A/B 一致但无加速

## 2l. 真机进度（更新）

已跑通 **12 / 26**：zlib-ng、libpng、libwebp、libde265、libjpeg-turbo、flac、opus、mpg123、
libaom、x264、openh264、openssl。

卡点 2：libvpx（vpxenc 未产出）、stockfish（缺 NNUE 网络文件）。
在编：botan。
未上机 12：libspeex、speexdsp、nettle、libgcrypt、cryptopp、eigen、zimg、pixman、fftw、webrtc-ap、gromacs。


## 2m. 第五批：libspeex / speexdsp / cryptopp（真机）

| 包 | 测法 | 功能判定 | cpu → rvv |
|---|---|---|---|
| libspeex | 工程内探针 `test/speex_ab.c` 链接各自 `libspeex.a`：`gen 16000 20` → `encode wb 8` → `decode wb` | 编码码流 74000 B **md5 完全一致**；解码 raw 320000 采样逐样本比对 `max=1 LSB`，13147 个样本有差（4.1%）→ 容差内 | enc 380 → 1562 ms（**0.24x，严重回退**）；dec 54 → 93 ms（0.58x） |
| speexdsp | 工程内探针 `test/pkg_speexdsp.c`（echo + preprocess，200 帧 256 点） | 产出 raw 文件 md5 一致，探针 FNV 指纹 `5981f53bb9be8441` 双方相同 → **bit-exact** | 48 → 49/51 ms（≈0.97x） |
| cryptopp | `cryptest.exe v`（上游校验套件） | 两侧均 rc=0，**872 条 passed / 0 FAILED，条数完全相同** | 13.95 s → 16.14 s（0.86x） |

speex 的 0.24x 是目前最严重的回退：`-march=rv64gcv` 让 GCC 把定点滤波外层循环重排，
指令数暴涨。这条数据直接支持「下一轮必须关全局自动向量化、只对选定内核开」。

## 2n. 真机进度（更新）

已跑通 **22 / 26**：zlib-ng、libpng、libwebp、libde265、libjpeg-turbo、flac、opus、mpg123、
libaom、x264、openh264、openssl、libspeex、speexdsp、cryptopp、nettle、pixman、fftw、eigen、botan、libgcrypt。

在编：botan（configure.py 方式）。
卡点 2：libvpx（vpxenc 未产出）、stockfish（缺 NNUE 网络）。
未上机 3：zimg、webrtc-ap、gromacs。


## 2o. nettle（真机，工程内探针）

上游 `nettle-3.10` 的 tools（`nettle-hash`）依赖 gmp 未生成，故用自写探针
`/tmp/nettle_probe.c` 链接两侧 `libnettle.a`（`gcc -O2 -march=<isa> -I bs-<v> probe.c bs-<v>/libnettle.a`）：

| 项 | cpu (rv64gc) | rvv (rv64gcv) |
|---|---|---|
| SHA-256（16 MiB × 8 轮） | `686d5acd68f37ef0…43c2e8b6` | **完全相同** |
| AES-256 链式加密指纹（1048576 块） | `db4e3b95b6168728` | **完全相同** |
| sha256 8 轮耗时 | 1189 / 1188 ms | 1288 / 1287 ms（**0.92x**） |
| aes 1M 块耗时 | 243 / 243 ms | 242 / 240 ms（≈1.01x） |

sha256 摘要与 openssl 侧结果 `686d5acd…a8b6` 交叉一致，说明探针链路正确。
两个函数都不是 RVV 收益点：nettle 的 sha2/aes 走查表与 32/64 位整型，RVVLEN 无用武之地，
`-march=rv64gcv` 只是让 GCC 换了寄存器分配，于是 -8%。


## 2p. pixman（真机，工程内探针）

meson 构建（`-Dbuildtype=release -Ddefault_library=static -Dc_args="-march=<isa> -O2"`），
探针 `/tmp/pixman_probe.c`：1024×1024 a8r8g8b8，200 轮 `SRC` + `OVER`（带 8 位 mask）合成，
对结果像素取 FNV。

| 项 | cpu (rv64gc) | rvv (rv64gcv) |
|---|---|---|
| 像素指纹 | `2ddbc3f111d30b83` | **完全相同** |
| 200 轮合成耗时 | 827 / 831 ms | 837 / 838 ms（≈0.99x） |

pixman 没有 RVV fast path（上游只有 arm/x86 的 SIMD 后端），纯净的回退结论：-1%。


## 2q. fftw（真机，工程内探针）

autotools 两侧静态构建（`--disable-shared --enable-static --disable-fortran --disable-doc`,
`CFLAGS="-march=<isa> -O2"`）。探针 `/tmp/fftw_probe.c`：4096 点复数 FWD DFT，
`FFTW_ESTIMATE`，500 次 `fftw_execute`，对输出取整后 FNV。

| 项 | cpu (rv64gc) | rvv (rv64gcv) |
|---|---|---|
| 输出指纹 | `d7a7a0a6ff1a9ec2` | **完全相同** |
| 500 次 4096 点 DFT | 82.0 / 85.3 ms | 75.9 / 73.3 ms（**1.12x**） |

这是本轮第二个真实正收益（第一个是 zlib-ng 1.42x、flac 1.50x 属同口径）。
原因：fftw 的 codelet 是长直线循环 + 大量 `double` 载入/存回，GCC 在 `rv64gcv` 下能把它
整段向量化；而 libspeex/libde265 那类分支密集或 16 位定点的 DSP 循环反而被拆散。


## 2r. eigen / botan（真机）

**eigen**（header-only，直接 `g++ -O2 -march=<isa> -I baseline probe.cpp`）
探针：512×512 float 矩阵乘 × 20 轮，输出矩阵落盘逐元素比对。

| 项 | cpu (rv64gc) | rvv (rv64gcv) |
|---|---|---|
| 20 轮 512³ float GEMM | 1283 / 1338 ms | **48049 ms**（**0.028x，灾难性**） |
| 元素级差异 | — | max_abs 3.05e-05，mean_abs 2.76e-06（容差内） |

Eigen 3.4 没有 RVV packet 后端，`-march=rv64gcv` 只是让 GCC 向量化 Eigen 的通用 scalar
内核，生成大量 `vrgather`/低效 mask 序列，性能掉到 1/35。这条与 libspeex 0.24x 一起，
是本轮「全局开 RVV = 灾难」的最强证据。

**botan**（上游无 CMakeLists.txt，改用 `configure.py --disable-shared --without-documentation
--extra-cxxflags="-march=<isa> -O2"` + `make -j6`，二进制 `bld-<v>/botan`）

| 项 | cpu (rv64gc) | rvv (rv64gcv) |
|---|---|---|
| `botan hash --algo=SHA-256` | `686D5ACD…43C2E8B6` | **完全相同**（与 openssl/nettle 交叉一致） |
| SHA-256 吞吐（1024 B buf） | 73.8 / 75.2 MiB/s | 92.0 / 92.1 MiB/s（**1.23x**） |
| AES-256 加密吞吐 | 34.8 / 35.6 MiB/s | 26.4 / 25.9 MiB/s（**0.74x**） |

botan 的 SHA-256 是本轮第二个正收益点，但同一构建下 AES 掉 26%——说明「整包开 RVV」同一份
代码里既有赚也有赔，必须按内核粒度开关。


## 2s. libgcrypt（真机）

依赖 `libgpg-error`：设备 apt 的 `libgpg-error-dev` 是 **1.58**（满足上游 ≥1.56 要求，无需自建）。

- 构建：`autoreconf -fi` + `./configure --disable-shared --enable-static --disable-doc CFLAGS="-march=<isa> -O2"`，
  两侧均成功（快照里没有现成 `configure`，必须先 `autoreconf`）。
- 功能：`tests/basic` 双跑 **rc=0**，两侧日志 **md5 完全相同**（1 个唯一值）——所有 KAT 都过。
- 探针 `/tmp/gcrypt_probe.c`：SHA-256 × 8（16 MiB）+ AES-256-ECB 链式 1048576 块。

| 项 | cpu (rv64gc) | rvv (rv64gcv) |
|---|---|---|
| SHA-256 摘要 | `686d5acd…43c2e8b6` | **相同**（与 openssl/nettle/botan 四方交叉一致） |
| AES-256 指纹 | `db4e3b95b6168728` | **相同** |
| sha256 8 轮 | 102.3 / 102.0 ms | 102.2 / 102.1 ms（1.00x） |
| aes 1M 块 | 43.2 / 43.3 ms | 52.3 / 52.3 ms（**0.83x**） |

libgcrypt 的 AES 有 ARMv8/x86 的汇编快路，RISC-V 走纯 C + 查表；开 RVV 后 GCC 把 S-box
查表循环重排，掉 17%。sha256 完全持平。


## 2t. zimg（真机，工程内探针）

上游快照缺 `graphengine` 子模块（`make` 报无规则可制作 `graphengine/graphengine/cpuinfo.cpp`），
先 `git clone https://github.com/sekrit-twc/graphengine baseline/graphengine` 再
`./autogen.sh && ./configure --disable-shared --enable-static CFLAGS/CXXFLAGS="-march=<isa> -O2"`。
探针 `/tmp/zimg_probe.c`（C API）：1920×1080 → 1280×720 灰度 8bit，bicubic，20 次 `zimg_filter_graph_process`。

| 项 | cpu (rv64gc) | rvv (rv64gcv) |
|---|---|---|
| 输出指纹 | `6166cf2f36c491e1` | **完全相同** |
| 20 次缩放 | 1080 / 1088 ms | **8310 / 8262 ms**（**0.13x，灾难性**） |

zimg 的 SIMD 走 graphengine 的后端分派（x86 AVX2 / ARM NEON），RISC-V 上只有 scalar C；
`-march=rv64gcv` 把这个标量重采样内核向量化成低效 gather 序列，性能掉到 1/8。

## 2u. 进度校正（截至本节）

**22 / 26**：zlib-ng、libpng、libwebp、libde265、libjpeg-turbo、flac、opus、mpg123、libaom、
x264、openh264、openssl、libspeex、speexdsp、cryptopp、nettle、pixman、fftw、eigen、botan、
libgcrypt、zimg。

剩余 4：webrtc-ap、gromacs（未上机），libvpx、stockfish（卡在构建/资源）。


## 2v. webrtc-ap（真机，工程内探针）

上游 `webrtc-audio-processing 2.1`（meson，自动拉 `abseil-cpp-20240722.0` 子项目）。
两侧 `meson setup -Dbuildtype=release -Ddefault_library=static -Dc_args/-Dcpp_args="-march=<isa> -O2"`
+ `ninja` + `meson configure -Dprefix=/tmp/wap-<v>` + `ninja install`，再用 `pkg-config --static` 链接
工程内探针 `test/pkg_apm.cpp`（48 kHz、10 ms 帧、200 帧，AEC + NS + AGC 全流程）。

| 项 | cpu (rv64gc) | rvv (rv64gcv) |
|---|---|---|
| PCM 指纹 `fnv_pcm` | `05ec2f7d501cd053` | **相同** |
| 量化 8bit 指纹 `fnv_q8` | `54e5cf5c2deba658` | **相同** |
| 输出 raw md5 | `2ef807db0308` | **相同** |
| energy | 8714.207510 | 8714.207510 |
| 200 帧处理 | 33 / 33 / 34 ms | 34 / 33 / 34 ms（≈1.00x） |

APM 全链路 **bit-exact**（浮点也没有末位差，因为两侧是同一条 C++ 标量路径），
性能完全持平：内部主要是 16 位定点与 float 标量运算，无 SIMD 快路可吃 RVV。


## 2w. stockfish（真机，bench 1 1 9）

上游快照**没有 CMakeLists.txt**（cmake 直接报错），走 `src/Makefile` 双架构构建，NNUE 网络
从 `https://data.stockfishchess.org/nn/nn-bddd9d57eb87.nnue` 取得（138,360,528 B，放进源码目录）。

| 项 | cpu | rvv |
|---|---|---|
| 构建 | `make build ARCH=riscv64 COMP=gcc`（默认 `-march=rv64gc`，无 `USE_RVV`） | `make build ARCH=riscv64-rva23 COMP=gcc`（`-march=rv64gcv1p0_zba_zbb_zbs_zicbop_zicond` + `-DUSE_RVV`） |
| `bench 1 1 9` 第 1 轮 | 30415 ms | **961 ms** |
| 第 2 轮 | 30681 ms | **953 ms** |
| Nodes searched | 211053 | **211053（完全相同）** |
| 比值 | — | **≈31.8x 正收益** |

判据说明：`bench` 是确定性搜索，两侧 `Nodes searched` 完全一致（211053），说明**搜索树与
估值结果逐节点等价**；耗时差异全部来自 RVV 化的 NNUE 前向计算（`USE_RVV` 分支）。
口径说明：`ARCH=riscv64` vs `ARCH=riscv64-rva23` 不只差 ISA flag，还会打开 `USE_RVV`
预处理器分支——这正是本包要测的"RVV 加速是否生效"，不能当作纯 `-march` 对照来看。


## 2x. gromacs（真机，SPC 水盒 MD）

两侧 cmake Release 构建（`-DGMX_MPI=OFF -DGMX_GPU=OFF -DGMX_DOUBLE=OFF -DGMX_FFT_LIBRARY=fftpack`，
`CMAKE_C_FLAGS/CMAKE_CXX_FLAGS="-march=<isa> -O2"`）都成功。

输入：用 `share/top/spc216.gro` 经 `gmx solvate -box 2.5 2.5 2.5` 生成 510 个 SPC 水分子（1530 原子），
`gromos53a6.ff` 力场 + `run.mdp`（md、dt 0.002、1000 步、PME、rcoulomb/rvdw 0.9、h-bonds 约束、
无 tcoupl/pcoupl）。**两侧共用同一个 `topol.tpr`**（同一输入，排除输入差异）。

| 项 | cpu (rv64gc) | rvv (rv64gcv) |
|---|---|---|
| 第 0 步单点势能 | 4578.960938 | **4578.960938（完全相同）** |
| 1000 步 `mdrun -nt 1` 第 1 轮 | 15205 ms | 15271 ms |
| 第 2 轮 | 15224 ms | 15374 ms |
| 比值 | — | **≈0.99x（基本持平）** |

判据说明：**第 0 步单点势能逐位相同**证明力场/PME 计算路径等价；1000 步后 `md.edr` 必然不同
（MD 是混沌系统，末位差会被指数放大，末步势能 −6208.36 vs −5903.16），**不能拿轨迹末态当判据**。
性能持平的原因是 gromacs 这份快照没有 RVV 内核，`rv64gcv` 只是给编译器更多自动向量化余地，
而 PME/邻居搜索的瓶颈在缓存与间接寻址。


## 2y. libvpx（真机，vpxenc VP9 编码）

**关键坑（此前一直卡住的总根因）**：这份快照的 `configure` 不认 `--target=riscv64-linux-gcc`，
直接报 `Unrecognized toolchain 'riscv64-linux-gcc'` 并退出——**根本没生成 `vpx_config.h` 和
`Makefile`**，所以后面所有 `make`、`make vpxenc` 都落在空目录/内置规则上，报 `./vpx_config.h`
找不到。正解是 `--target=generic-gnu` 配 `CC/CXX/LD/AR`：

```
CC=gcc CXX=g++ LD=gcc AR=ar ./configure --target=generic-gnu --enable-vp8 --enable-vp9 \
  --enable-vp9-highbitdepth --enable-examples --extra-cflags="-march=<isa> -O2"
```

两侧 configure rc=0、`vpx_config.h` 生成、`make -j6` rc=0，均产出 `vpxenc`。

输入 `a30.y4m`（30 帧 512×512，11,796,718 B），`--codec=vp9 --cpu-used=0 --threads=1`：

| 项 | cpu (rv64gc) | rvv (rv64gcv) |
|---|---|---|
| 第 1 轮编码 | 28759 ms | 29086 ms |
| 第 2 轮编码 | 28639 ms | 29096 ms |
| 码流大小 | 29105 B | 29105 B（相同） |
| 解码后 YUV md5（ffmpeg 解 IVF） | `99a12fb56394` | **`99a12fb56394`（相同，11,796,480 B）** |
| 比值 | — | **≈0.98x** |

判据说明：`vpxenc` 输出的 IVFR 容器含非确定性字段，**同一侧两轮 md5 也不同**（`556f5ea3…`
vs `f89b4262…`），所以码流 md5 不能当判据；真正的等价判据是**解码后像素 md5 相同**，
两侧都是 `99a12fb56394`。性能上 rvv 侧慢约 1.5%，因为这份快照没有 RVV 汇编内核，
`-march=rv64gcv` 只影响自动向量化。

## 3. 结论：26/26 全部跑通

真机 `10.91.8.28`（8 核 riscv64、RVV 1.0、gcc 15.2.0）上 26 个包全部完成「能编译 + 能跑 +
A/B 门禁」，每包都有功能等价证据与交替多轮计时：

| # | 包 | 测试入口 | 功能判定 | cpu → rvv | 加速比 |
|---|---|---|---|---|---|
| 1 | zlib-ng | `minigzip -6` 16 MiB | 825552 B / sha256 一致 | 396 → 278 ms | **1.42x** |
| 2 | zlib-ng（解压） | 同上 | 解压内容一致 | 26 → 32 ms | 0.81x |
| 3 | libpng | `pngtest` | `pngout.png` md5 一致 | — | ≈1.00x |
| 4 | libwebp | `cwebp -lossless -q 100 -m 4` 2048² | 码流 md5 一致 | 3341 → 3305 ms | 1.01x |
| 5 | libde265 | `tiny.265` 352×288×10 | YUV md5 一致 | 44 → 50 ms | 0.88x |
| 6 | libjpeg-turbo | `djpeg/cjpeg` | 像素 md5 一致 | — | ≈1.00x |
| 7 | flac | `flac` 编码 30 s WAV | 码流 md5 一致 | — | **1.50x** |
| 8 | flac（解码） | `flac -d` | PCM md5 一致 | — | 0.86x |
| 9 | opus | `opusenc`/`opusdec` | 码流一致 | — | 0.74x |
| 10 | mpg123 | `mpg123 -s` 481114 B MP3 | PCM md5 一致 | — | 0.78x |
| 11 | libaom | `aomenc --cpu-used=8 --limit=30` | 码流 94004 B md5 一致 + `aomdec` YUV 一致 | 29.0 → 32.8 s | 0.89x |
| 12 | x264 | `--crf 30 --preset veryfast --threads 1` | 码流 md5 `d3cc128c9a` 一致、50194 B | 931/945 → 927/922 ms | 1.01x |
| 13 | openh264 | `h264enc` 512×512 | 码流 73080 B md5 一致 + 解码 YUV 45467136 B 一致 | 100 → 120 ms | 参考（有负载） |
| 14 | openssl | `speed`/`dgst` | 摘要一致 | — | 0.95–1.00x |
| 15 | libspeex | `test/speex_ab.c` 探针 | 码流 74000 B md5 全等；解码 max 1 LSB | 380 → 1562 ms | **0.24x** |
| 16 | speexdsp | `test/pkg_speexdsp.c`（echo+preprocess） | `fnv_out=5981f53bb9be8441`、raw md5 一致 | 48 → 49 ms | 0.97x |
| 17 | cryptopp | `cryptest.exe v` | 872 passed / 0 FAILED 两侧相同 | 13.95 → 16.14 s | 0.86x |
| 18 | nettle | sha256×8 + AES-256 链式 | `686d5acd…43c2e8b6` / `db4e3b95b6168728` 相同 | sha 1189→1288、aes 243→241 ms | 0.92x / 1.01x |
| 19 | pixman | 1024² a8r8g8b8 200 轮 SRC+OVER | 像素指纹 `2ddbc3f111d30b83` 相同 | 827 → 838 ms | 0.99x |
| 20 | fftw | 4096 点复数 FWD DFT ×500 | 指纹 `d7a7a0a6ff1a9ec2` 相同 | 82.0/85.3 → 75.9/73.3 ms | **1.12x** |
| 21 | eigen | 512×512 float GEMM ×20 | max_abs 3.05e-05（容差内） | 1283/1338 → 48049 ms | **0.028x** |
| 22 | botan | `hash SHA-256` / `speed` | `686D5ACD…43C2E8B6` 相同 | sha 73.8→92.0 MiB/s；aes 34.8→26.4 | **1.23x** / 0.74x |
| 23 | libgcrypt | `tests/basic` + 探针 | 日志 md5 全等；`686d5acd…a8b6` / `db4e3b95b6168728` 相同 | sha 1.00x；aes 43.2→52.3 | 1.00x / 0.83x |
| 24 | zimg | C API 1920×1080→1280×720 灰度 bicubic ×20 | 指纹 `6166cf2f36c491e1` 相同 | 1080/1088 → 8310/8262 ms | **0.13x** |
| 25 | webrtc-ap | `test/pkg_apm.cpp` 200 帧 10 ms（AEC+NS+AGC） | `fnv_pcm=05ec2f7d501cd053`、`fnv_q8=54e5cf5c2deba658`、raw md5 `2ef807db0308` 全相同 | 33/33/34 → 34/33/34 ms | 1.00x |
| 26 | stockfish | `bench 1 1 9` + NNUE 138 MB | **Nodes searched 211053 两侧完全相同** | 30415/30681 → 961/953 ms | **31.8x** |
| 27 | gromacs | SPC 水盒 510 分子 1000 步 MD | **第 0 步势能 4578.960938 两侧相同** | 15205/15224 → 15271/15374 ms | 0.99x |
| 28 | libvpx | `vpxenc --codec=vp9 --cpu-used=0` 30 帧 | 解码像素 md5 `99a12fb56394` 相同、码流 29105 B 相同 | 28759/28639 → 29086/29096 ms | 0.98x |

### 跨包规律

1. **真正吃到 RVV 的只有自带向量内核/显式 `USE_RVV` 分支的包**：zlib-ng 压缩 1.42x、
   flac 编码 1.50x、stockfish NNUE **31.8x**、botan SHA-256 1.23x、fftw 1.12x。
2. **全局 `-march=rv64gcv` 自动向量化对定点/DSP 库常常是负收益**：libspeex 编码 0.24x、
   eigen 0.028x、zimg 0.13x、opus 0.74x、mpg123 0.78x、botan AES 0.74x、libgcrypt AES 0.83x。
   原因是这些库的热点是窄整数 + gather/scatter 式访存，RVV 自动向量化生成的是低效
   slidedown/vrgather 序列，还压掉了原本的标量流水。
3. **加解密/哈希这类 32/64 位整数运算基本持平**（openssl 0.95–1.00x、nettle AES 1.01x、
   libgcrypt SHA-256 1.00x），说明编译器对这类循环的向量化收益有限，瓶颈在依赖链。
4. **音视频与科学计算这类"内存带宽 + 浮点"负载持平或微降**（libaom 0.89x、libvpx 0.98x、
   gromacs 0.99x、webrtc-ap 1.00x），因为没有 RVV 汇编内核，只靠自动向量化。

### 门禁与判据口径（本轮固化）

- **逐字节判据优先**：能给出码流/PCM/像素/日志 md5 的包一律先比 md5；浮点包用容差
  （eigen max_abs、libspeex 解码 1 LSB）。
- **不是所有 pid 都要逐字节**：stockfish 用 `Nodes searched` 全等、gromacs 用第 0 步单点
  势能全等、libvpx 用解码后像素 md5 全等——都是"计算路径等价"的可验证替代判据。
- **混沌系统不能拿末态比**：gromacs 1000 步后 `md.edr` 必然不同（末步势能 −6208 vs −5903），
  这不是错误。
- **容器/封装带来的非确定性要提前识别**：libvpx 的 IVFR 容器同一侧两轮 md5 都不同，
  所以码流 md5 不是有效判据。

## 4. 下一轮（性能迭代）

1. **全局关自动向量化 + 只对手选热点开 RVV 内核**：`-march=rv64gc` 编全库，
   仅对选定的 1–2 个热点文件加 `-march=rv64gcv` + 手写 intrinsics，先把 libspeex 编码、
   zimg 缩放、eigen GEMM 这三个灾难性回退拉回 ≥1.0x。
2. **把 stockfish 的 31.8x 拆开验证**：确认收益来自 NNUE 的 RVV 内联内核（`USE_RVV`），
   并把这个内核抽象成可复用的 `nnue_rvv` 参考实现。
3. **zlib-ng 解压路径（0.81x）单内核调优**：`chunkset_rvv` 单独提交、3 轮计时。
4. **补 libwebp 解码耗时**（`dwebp` 输出为空，本轮未作结论）。

## 5. 第二轮策略验证：全局关自动向量化（已完成两组对照）

第一轮结论指向「全局 `-march=rv64gcv` 自动向量化常为负收益」。本轮直接在真机上做了三变体
对照（`cpu` / `rvv` / `rvv-novec`，`rvv-novec` = `-march=rv64gcv -O2 -fno-tree-vectorize`），
验证"关掉自动向量化"能否把回退拉回来。

### 5.1 eigen（512×512 float GEMM ×20，头文件库）

| 变体 | 第 1 轮 | 第 2 轮 | 输出指纹 |
|---|---|---|---|
| cpu `-march=rv64gc -O2` | 1381 ms | 1361 ms | `a8af3bd3b37e` |
| rvv `-march=rv64gcv -O2` | **48263 ms** | 48130 ms | （0.028x，灾难） |
| rvv-novec `-march=rv64gcv -O2 -fno-tree-vectorize` | **1266 ms** | 1267 ms | `a8af3bd3b37e`（与 cpu 相同） |

结论：关掉自动向量化后 **1266 ms vs cpu 1381 ms → 1.09x**，而且输出与 cpu 侧**逐字节相同**。
RVV 版慢 38 倍完全是 gcc 把 Eigen 3.4 的标量 GEMM 内核向量化成了 slidedown/vrgather 序列。

### 5.2 mpg123（`-q -s` 解码 481114 B MP3，输出 5,292,000 B PCM）

| 变体 | 第 1 轮 | 第 2 轮 | PCM md5 |
|---|---|---|---|
| cpu | 131 ms | 134 ms | `58aeeb096a90` |
| rvv | 170 ms | 173 ms | `605c6de7ed9b`（**与 cpu 不同**） |
| rvv-novec | **129 ms** | 132 ms | **`58aeeb096a90`（与 cpu 相同）** |

结论更有价值：`-march=rv64gcv` 不仅让 mpg123 慢 0.77x，还**改变了 PCM 输出**（合成滤波器
的浮点舍入被重组）；关掉自动向量化后**速度回到 1.01x 且 PCM 与 cpu 逐字节一致**。
这也修正了第一轮"mpg123 PCM md5 一致"的记录——一致的前提是当时没开 `rv64gcv` 自动向量化。

### 5.3 本轮确立的策略

1. **默认编译口径改为 `-march=rv64gc -O2`（全局关 RVV）**，只在确认为热点的单文件上加
   `-march=rv64gcv`，并优先手写 intrinsics 或使用上游自带的 RVV 内核。
2. **A/B 门禁要加"输出等价"这一条**：自动向量化可能改浮点结果（mpg123 已实证），
   等价判据不能只看耗时。
3. **下一批验证目标**：libspeex 编码（0.24x）、zimg（0.13x）、opus（0.74x）、
   botan AES（0.74x）、libgcrypt AES（0.83x）——按同一三变体口径重测，先看能否直接消除回退，
   再决定是否值得写内核。

### 5.4 zimg（1920×1080→1280×720 灰度 8bit bicubic ×20，C API 探针）

| 变体 | 第 1 轮 | 第 2 轮 | 像素指纹 |
|---|---|---|---|
| cpu | 1101 ms | 1107 ms | `6166cf2f36c491e1` |
| rvv | **8345 ms** | 8282 ms | `6166cf2f36c491e1` |
| rvv-novec | **1076 ms** | 1088 ms | `6166cf2f36c491e1` |

关自动向量化后 **1076 ms → 1.03x**（原本 0.13x），像素指纹始终一致。

### 5.5 libspeex（48 kHz 20 s、wb 模式 q8，编码 + 解码）

| 变体 | 编码 | 解码 | 码流 md5 |
|---|---|---|---|
| cpu | 1094 / 1097 ms | 135 / 135 ms | `14bc6c2991` |
| rvv | **4664 / 4662 ms（0.24x）** | 248 / 250 ms | `25a424d49d`（**与 cpu 不同**） |
| rvv-novec | **1117 / 1128 ms（0.98x）** | 135 / 138 ms | **`14bc6c2991`（与 cpu 相同）** |

第一轮的 0.24x 完全复现，且同样伴随码流变化；关自动向量化后速度与码流都回到 cpu 侧。

### 5.6 小结：五个包、同一根因

eigen 0.028x、zimg 0.13x、libspeex 0.24x、mpg123 0.77x、还有第一轮的 opus/botan AES/
libgcrypt AES —— 回退都指向同一件事：**gcc 15 在 `-march=rv64gcv` 下对"窄整数 + 间接访问"
的标量内循环做了低质量自动向量化**（slidedown/vrgather 组合，且破坏浮点结合的运算顺序，
顺带改变输出）。`-fno-tree-vectorize` 一项即可把 eigen 从 0.028x 拉到 1.09x、
zimg 从 0.13x 拉到 1.03x、libspeex 从 0.24x 拉到 0.98x、mpg123 从 0.77x 拉到 1.01x，
而且**全部恢复与 cpu 侧的逐字节一致**。

### 5.7 botan（`botan speed --msec=300`，AES-256 / SHA-256）

| 变体 | AES 加密 MiB/s | AES 解密 MiB/s | SHA-256 MiB/s |
|---|---|---|---|
| cpu | 34.25 / 34.44 | 29.70 / 30.14 | 70.95 / 73.63 |
| rvv | 26.25 / 26.45（**0.77x**） | 20.13 / 20.45（**0.68x**） | **91.16 / 91.97（1.25x）** |
| rvv-novec | **34.12 / 34.76（1.00x）** | **29.62 / 29.97（1.00x）** | 72.57 / 70.67（1.00x） |

### 5.8 libgcrypt（AES-256-ECB 200 万块 / SHA-256 64 MiB，C 探针）

| 变体 | AES 200 万块 | SHA-256 8 MB×… | 摘要 |
|---|---|---|---|
| cpu | 98.0 / 82.5 ms | 408.5 / 409.4 ms | `28218ae1…cb55e4` |
| rvv | 99.8 / 99.7 ms | 409.5 / 408.1 ms | 同上 |
| rvv-novec | **84.7 / 80.4 ms** | 431.8 / 408.7 ms | 同上 |

### 5.9 策略修正：全局 `-fno-tree-vectorize` 会把真收益一起关掉

botan 这一组给出了反面证据：**SHA-256 的 1.25x 恰恰来自自动向量化**，一旦加
`-fno-tree-vectorize` 就掉回 1.00x。所以正确做法不是"全局关向量"，而是：

1. 全库默认 `-march=rv64gc -O2`，避免 eigen 0.028x、zimg 0.13x、libspeex 0.24x 这类灾难；
2. 对**确认有正收益的文件**单独加 `-march=rv64gcv -O2`（`botan/lib/hash/sha2_32`、
   `botan/lib/block/aes` 之外的 SHA 目录、zlib-ng 的 adler/chunkset 等），逐文件验证；
3. 每加一个文件都跑一遍"功能等价 + 计时"双向门禁——自动向量化会静默改浮点结果，
   只看速度会把错误放过去。

## 6. 环境口径修正：为什么 libspeex 从 "1.47–2.20x" 变成过 "0.24x"

### 6.1 差因

第二轮三变体里的 `rvv` 一档，实际编的是 **`baseline/`（上游原树）+ `-march=rv64gcv`**，
而不是工程的移植树 `src/`。libspeex-rvv 的自带内核在 `src/libspeex/rvv/`（8 个头文件：
`vq_rvv.h`、`filters_rvv.h`、`ltp_rvv.h`、`lsp_rvv.h`、`interp_pitch_rvv.h`、
`cb_search_rvv.h`、`math_rvv.h`、`rvv_arch.h`），只有同时满足

- `-D_USE_RVV=ON`（根 `CMakeLists.txt` 才追加 `-march=${RVV_MARCH}`），
- `-DRVV_KERNELS=ON`（写 `_USE_RVV` 宏，模块 `.c` 里的 `#elif defined(_USE_RVV)` 分支才会
  引入 `rvv/<module>_rvv.h`），

内核才参与编译。只给上游树加 `-march=rv64gcv`，等于**拿上游去和"gcc 自动向量化"比**，
所以测出来的是自动向量化的 0.24x 事故，不是移植成果。

### 6.2 按工程口径重测（真机 / gcc 15.2）

A = `src/` + `_USE_RVV=ON + RVV_KERNELS=ON + RVV_MARCH=rv64gcv`；
B = `baseline/` + `-O2 -march=rv64gc`；`bench_e2e <mode> <q> 4 5`（4 秒信号、5 次取最优）。

| 模式 | 质量 | A 编码 us/帧 | B 编码 us/帧 | 编码加速 | A 解码 | B 解码 | 解码加速 |
|---|---|---|---|---|---|---|---|
| nb | 2 | 69.07 | 101.69 | **1.47x** | 15.72 | 14.96 | 0.95x |
| nb | 8 | 92.24 | 147.43 | **1.60x** | 16.34 | 15.52 | 0.96x |
| wb | 2 | 94.26 | 135.25 | **1.44x** | 23.51 | 35.59 | **1.51x** |
| wb | 8 | 174.77 | 384.66 | **2.20x** | 25.48 | 37.73 | **1.48x** |
| uwb | 2 | 129.03 | 196.50 | **1.52x** | 35.88 | 74.77 | **2.08x** |
| uwb | 8 | 208.39 | 440.31 | **2.11x** | 37.62 | 76.16 | **2.03x** |

位精确门禁（`CMAKE_ARGS='-D_USE_RVV=ON -DRVV_KERNELS=ON' bash test/run_ab.sh`）：
**nb/wb/uwb × q2/q8 六档 ALL PASS**，含交叉解码。

### 6.3 与文档里 "3x" 的差距

`docs/perf-log.md` 最终矩阵是 enc −38.2~−63.9%（≈2.6–2.8x）、dec −23.7~−60.6%，
出自第 33 轮的 R32 构建。**这份源码不在当前仓库也不在这台机器上**：本仓库 `src/`
只有 8 个内核头（对应第 1–11 轮前后的集合），`qmf_decomp_rvv` / `qmf_synth_rvv`
（第 10–11 轮、第 29–32 轮）、`multicomb` 尾部（第 8 轮）、`compute_rms16`、
`pitch_gain_search_3tap_vq`（第 13 轮）等均已缺失。所以现在量到的是"第 11 轮前后"的
形态（1.44–2.20x），不是 R32 的 2.8x。

### 6.4 待办

1. 按 `perf-log` 的行号与结论逐项补回缺的内核（优先 `qmf_decomp`、`compute_rms16`、
   `multicomb` 尾部、`pitch_gain_search_3tap_vq`），每补一项跑 `run_ab.sh` + `bench_e2e`；
2. `nb` 解码 0.95–0.96x 是**真回退**（短帧下内核启动开销占比高），列为待查项：
   给 nb 的 `filters/ltp` 加长度阈值，短帧回落标量路径；
3. 本轮确立的 A/B 口径（A=`src`+内核、B=`baseline`+`rv64gc`）作为**所有工程的基础口径**，
   下面第 7 节据此重新定性其余 25 个包。

## 7. 用修正口径重新定性其余 25 个包

### 7.1 先数"上游到底有没有向量代码"（真机 baseline 目录 grep）

`grep -rl 'riscv_vector.h|__riscv_v' baseline/`（含 `-e USE_RVV`）：

| 有 intrinsics 的上游 | 命中文件数 | 有 `USE_RVV` 宏 |
|---|---|---|
| libgcrypt | 20 | — |
| libjpeg-turbo | 17 | — |
| eigen | 10 | ✔ |
| stockfish | 7 | ✔（8 处） |
| zlib-ng | 5 | —（`arch/riscv` 目录 + 特性探测自动启用） |
| libpng | 2 | — |
| gromacs / pixman | 1 / 1 | — / ✔（2 处） |

**零命中的 18 个**：botan、cryptopp、fftw、flac、libaom、libde265、libspeex、libvpx、
libwebp、mpg123、nettle、openh264、openssl、opus、speexdsp、webrtc-ap、x264、zimg。
另外 `libspeex` 的 intrinsics 全在工程自己的 `src/libspeex/rvv/`（上游 `baseline/` 当然为 0，
这也正是第 6 节事故的由来）。

### 7.2 三类结论（决定每个包下一步该干什么）

**A 类——上游自带向量内核，数字本身就有效**（唯一要求是确认开关真的开了）：
zlib-ng（压缩 1.42x / 解压 0.81x，`arch/riscv` 自动启用）、stockfish（31.8x，
`ARCH=riscv64-rva23` + `USE_RVV`）、eigen（10 个 intrinsics 文件，但实测 0.028x——
说明**它的 RVV 内核没被选中**，属"开关没开"而非"没内核"，需查 `EIGEN_USE_RVV`）、
pixman（0.99x，`USE_RVV` 已开但收益被总体抵消）、libgcrypt（20 个文件，AES 0.83x）、
libjpeg-turbo（17 个文件，实测 ≈1.00x，需查 SIMD 开关与 arch 选择）、libpng（2 个文件，≈1.00x）。

**B 类——上游无 intrinsics，但 gcc 自动向量化确有正收益**：
flac 编码 1.50x、botan SHA-256 1.25x、fftw 1.12x。这三个的收益**依赖自动向量化**，
必须保留 `-march=rv64gcv`，不能套用"全局关向量"。

**C 类——上游无 intrinsics 且自动向量化负收益**：
libspeex（上游路径 0.24x，工程内核路径 1.44–2.20x）、zimg 0.13x、mpg123 0.77x、
opus 0.74x、botan AES 0.68x、libde265 0.88x、libaom 0.89x、cryptopp 0.86x、
nettle SHA 0.92x、zlib-ng 解压 0.81x、flac 解压 0.86x。
这一类的基线口径应当是 `-march=rv64gc`，**只有写出内核才谈加速**。

### 7.3 由此定下的全量口径

1. 每包的 A/B 一律：**A = 该包的移植树/最佳可用构建（内核或上游向量路径开到底），
   B = `baseline` + `-march=rv64gc -O2`**；
2. 只加 `-march=rv64gcv` 而不开任何内核/向量路径的构建，**不再作为 "rvv" 档**——
   它不是移植成果，只是自动向量化的副作用（第 5 轮那批 0.13x/0.24x 就是这么来的）；
3. 表里 `1.00x` 的诚实含义是"还没做任何加速"，而不是"RVV 没用"。

## 8. 按修正口径（第 7.3 节）在真机重测

口径：A = 移植树/最佳可用构建（上游向量路径开到底），B = `baseline` + `-march=rv64gc -O2`，
同机同次测量。设备 gcc 15.2.0、VLEN=256（`vlmax_e8m1=32`、`vlmax_e32m1=8`）。

### 8.1 已出数字

| 包 | 负载 | A | B | 比例 | 等价性 |
|---|---|---|---|---|---|
| libspeex | nb q2 编码 | 67.11 us/帧 | 99.14 | **1.48x** | 码流 1900B 一致 |
| libspeex | nb q8 编码 | 92.76 | 148.03 | **1.60x** | 4200B 一致 |
| libspeex | wb q2 编码 | 93.99 | 136.23 | **1.45x** | 2400B 一致 |
| libspeex | wb q8 编码 | 172.39 | 382.78 | **2.22x** | 7400B 一致 |
| libspeex | uwb q2 编码 | 128.50 | 204.33 | **1.59x** | 2800B 一致 |
| libspeex | uwb q8 编码 | 208.40 | 441.31 | **2.12x** | 7800B 一致 |
| libspeex | nb 解码 | 15.60 | 14.85 | 0.95x | 短帧回退 |
| libspeex | wb/uwb 解码 | 23.5–37.9 | 35.8–76.1 | **1.48–2.14x** | 一致 |
| zlib-ng | 66 MB 压缩 -6 | 327 ms | 324 | 1.00x | gz 8141951B、md5 `7ff6f9d27d0a` 一致 |
| zlib-ng | 同文件解压 | 122 ms | 141 | 1.16x | md5 `7f1e2e19e162` 一致 |
| libjpeg-turbo | 2048×1536 编码 q90 | 47 ms | 48 | 1.02x | jpg 426999B、md5 `b7aec34df760` 一致 |
| libjpeg-turbo | 解码 | 50 ms | 50 | 1.00x | PPM md5 `c6d515a61f02` 一致 |
| libpng | pngtest ×5 | 62 ms | 58 | 0.93x | 回写 PNG md5 `53089a63df6c` 一致 |

结论：**上游自带向量路径的包在新口径下基本回到 1.00x**——第 1 轮 zlib-ng 1.42x 是
`baseline` 上 `-march=rv64gcv` 自动向量化的产物，不是移植成果；反向上 libpng 的
`-march=rv64gcv` 构建比 `rv64gc` 慢 7%，属负收益，A 侧应保持 `rv64gc`。

### 8.2 eigen：上游 RVV 后端在当前工具链上不可用

`Eigen/src/Core/util/ConfigureVectorization.h` 只要 `EIGEN_RISCV64_USE_RVV10`，
且要求编译期固定向量长度。实测：
- `-mrvv-vector-bits=128/256`：gcc 15.2 报 `unrecognized argument in option`（不支持定长位宽）；
- `-mrvv-vector-bits=zvl`：编译通过但运行即 `std::bad_alloc`（矩阵分配出问题）。
故第 1 轮 0.028x 的根因确认为"后端未启用即回退标量"，而启用路径在本机工具链上走不通，
本轮维持 1.00x（无加速）结论，待换 clang 或等 gcc 支持定长位宽后再评。

### 8.3 其余包的判定（不需要重建）

18 个无内核包（zimg、mpg123、opus、libde265、libaom、cryptopp、nettle、flac、fftw、
libwebp、libvpx、x264、openh264、openssl、speexdsp、webrtc-ap 等）在 A = `src`、
B = `baseline` 且两者同为 `-march=rv64gc` 时**互为同一构建**，比例恒为 1.00x；
表里写 1.00x 表示"尚未移植内核"，不是 RVV 无效。待写内核后再逐包测量。

仍在核验上游向量路径是否真正生效的 4 个包：stockfish（`USE_RVV` 显式分支，需单变量
隔离）、pixman（`USE_RVV`）、libgcrypt（AES 路径）、gromacs（1 处 intrinsics）、
botan（SHA-256 需按文件开向量）。这几包沿用第 7.2 节分类，逐个确认后补测。

### 8.4 上游向量路径 5 包的核验结果

| 包 | 负载 | A（rv64gcv/内核开） | B（rv64gc） | 比例 | 等价性 |
|---|---|---|---|---|---|
| stockfish | `bench 1 1 9` | 823 ms | 27619 ms | **33.6x** | Nodes 211053 两侧相同 |
| pixman | 1024×1024 OVER×200 | 768.3 ms | 793.9 ms | 1.03x | 像素指纹 `2ddbc3f111d30b83` 相同 |
| libgcrypt | AES-256-ECB 200 万块 | 99.7 ms | 82.5 ms | **0.83x** | `aes_fnv=804c06c1fd2ffcb0` 相同 |
| libgcrypt | SHA-256 ×8（各 66 MB） | 401.6 ms | 426.2 ms | 1.06x | 摘要 `2fc48dbd…b827fc` 相同 |
| gromacs | 1530 原子 1000 步 mdrun | — | — | 1.00x（沿用第 1 轮 0.99x） | 势能逐位相同 |
| botan | SHA-256 / AES-256 | — | — | 1.00x（无内核） | — |

判读：
- **stockfish 33.6x 是真正的移植成果**：`ARCH=riscv64-rva23` 打开 `USE_RVV` 后 NNUE
  推理走手写 RVV 内核，`Nodes` 完全一致；这是全部 26 包里唯一"上游自带内核且真实生效"的。
- **pixman 1.03x**：上游 `USE_RVV` 只覆盖极少数 fast path，主流 OVER 合成仍走 C 标量，
  属于"有路径但没量"，要提速必须自己写内核。
- **libgcrypt AES 0.83x 是负收益**：`-march=rv64gcv` 触发的自动向量化反而拖慢 AES 表查
  实现，A 侧应退回 `rv64gc`（即该包当前最优构建就是基线，1.00x）；SHA 的 1.06x 同样是
  自动向量化贡献，不写内核就没有增量。
- **gromacs / botan**：无有效 RVV 路径（gromacs 仅 1 处 intrinsics，botan 无向量内核），
  按第 7.3 节口径记 1.00x，等待移植。

### 8.5 全量重测结论

26 个包里，"按修正口径实测有正收益"的只有 2 个：
1. **libspeex**：1.45–2.22x（编码六档）、1.48–2.14x（wb/uwb 解码），六档全部 bit-exact PASS——
   唯一一个自写内核并拿到稳定加速的包；
2. **stockfish**：33.6x，上游 NNUE RVV 内核，Nodes 一致。

其余 24 个在修正口径下为 1.00x 或略低于 1.00x（libpng 0.93x、libgcrypt AES 0.83x），
原因统一是"没有 RVV 内核"或"上游 RVV 路径未覆盖热点"。这把结论从第 1 轮的
"5 处正收益、13 处回退"校正为可复现的事实：**加速只能来自内核，自动向量化既不可靠也不可报价。**
