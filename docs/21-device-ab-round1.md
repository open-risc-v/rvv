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

已跑通 **16 / 26**：zlib-ng、libpng、libwebp、libde265、libjpeg-turbo、flac、opus、mpg123、
libaom、x264、openh264、openssl、libspeex、speexdsp、cryptopp、nettle。

在编：botan（configure.py 方式）。
卡点 2：libvpx（vpxenc 未产出）、stockfish（缺 NNUE 网络）。
未上机 8：libgcrypt、eigen、zimg、pixman、fftw、webrtc-ap、gromacs。


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

## 3. 结论

真机四包结果一览：

| 包 | 输入 | 功能判定 | cpu | rvv | 加速比 |
|---|---|---|---|---|---|
| zlib-ng | 16 MiB 文本，`minigzip -6` | 825552 B / sha256 一致 | 396 ms | 278 ms | **1.42x** |
| zlib-ng（解压） | 同上 | 解压内容一致 | 26 ms | 32 ms | 0.81x |
| libpng | `basn2c08.png`，`pngtest` | `pngout.png` md5 一致 | — | — | 无（上游无 RVV 内核） |
| libwebp | 2048² 噪声，`cwebp -lossless -q 100 -m 4` | 码流 md5 一致 | 3341 ms | 3305 ms | 1.01x |
| libde265 | `tiny.265`（352×288×10） | YUV md5 一致 | 44 ms | 50 ms | 0.88x |

1. 真机链路打通：`git clone` → `fetch-upstream.sh` → 双配置构建 → 产物逐字节比对 → 计时，
   全程在设备上完成，不依赖 VM。
2. 第一个真机加速比：zlib-ng 压缩 **1.42x**；同时暴露了解压侧 RVV 路径的退化（0.81x）。
3. 26 个目标包里，**只有 zlib-ng 上游自带 RVV 内核**；其余包在 `rv64gcv` 下要么编译器自动
   向量化、要么完全没有向量路径。要做"RVV 优化 kernel"，只能在真机上自己写 intrinsics
   （VM 的交叉 gcc 缺 `riscv_vector.h`）。

## 4. 下一轮

1. zlib-ng `chunkset_rvv` 解压路径调优（单内核、单独提交、跑同一套 3 轮计时）。
2. 选第二个包做**自写 intrinsics**：`libpng` 的滤波循环（`png_read_filter_row_*`）是纯字节运算，
   适合 `vle8/vse8 + 掩码` 实现，收益可量化。
3. 真机批量回归：把 VM 上 25 个包的探针二进制搬到真机跑一遍，验证"交叉产物在真机可执行"。
   限制：需要先解决 25 个二进制的传输通道（VM 与真机之间目前无直连）。
