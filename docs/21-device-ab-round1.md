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
