# 11 构建顺序（按依赖关系重排）

> 上一版波次（`docs/05` §2 的人工初版、`docs/07` §5 的 AI 排期）是按"品类"分批：
> W2 媒体、W3 音频、W4 安全……。本文件把顺序改成**由依赖关系推出来**：
> 先把被依赖的东西做完，再让依赖方进波次。
>
> 一句话结论：**48 个包里真正的编译依赖只有 4 条**，所以顺序约束主要来自
> "性能归因"和"集成验证"，而不是"不装 A 就编不出 B"。重排后 29 个项目的波次变化，
> 主线从 24.0 周变为 **24.6 周（2026-11-26 → 2027-05-07）**。

## 1. 依赖数据从哪来

唯一真值源是 `data/deps.csv`（52 条边，列：`from_pkg,from_project,to_pkg,to_project,kind,evidence,note`）。
每条边都带 `evidence`，取自**本地这份上游源码**，不是凭印象：

| 抓取位置 | 例子 |
|---|---|
| 构建系统声明 | libpng `CMakeLists.txt` 要 `ZLIB`（`PNG_BUILD_ZLIB` 已废弃，走 `ZLIB_ROOT`）；libgcrypt `configure.ac:77` 的 `NEED_GPG_ERROR_VERSION=1.56` |
| configure 开关 | ffmpeg `configure` 的 External library support 段：`--enable-libvpx/libaom/libopenh264/libx264/libx265/libzimg/libopus/libwebp` |
| 依赖关系行 | ffmpeg 的 `libvpx_vp9_decoder_deps="libvpx"`、`h264_decoder_deps="libopenh264"` |
| 上层工程 CMake | opencv `CMakeLists.txt`：`WITH_JPEG/WITH_PNG/WITH_WEBP/WITH_FFMPEG` 默认 ON，Linux 走系统库 |
| 自带上游拷贝 | chromium `DEPS`：`third_party/libjpeg_turbo`、`libvpx`、`libwebp`、`ffmpeg` |

### 三类边（kind 决定"卡不卡顺序"）

| kind | 条数 | 含义 | 对排期的作用 |
|---|---|---|---|
| **hard** | 4 | 不装前置就编不过 / 跑不起来 | 前置换波次更早（且必须更早） |
| **bench** | 21 | 编得过，但**归因基准**必须先有前置 | 前置换波次更早（外置路径的加速比才可解释） |
| **soft** | 27 | 只是经验复用 / 可选开关 | 只记录，不阻塞 |

### 四条硬边

```
zlib-ng  → libpng          （libpng 无 zlib 无法编）
openssl  → node            （node 用系统 openssl 做 TLS/crypto）
ffmpeg   → vlc             （vlc 的 demux/decode 全走 libav*）
eigen    → pcl             （pcl find_package(Eigen3) 必需）
```

## 2. 关键洞察：依赖是"稀疏"的

48 个项目里只有 4 条编译依赖，原因有三：

1. **大多数包自带实现**：ffmpeg 有原生 FLAC/MP3/HEVC/VP9 解码器；x265 自带分析用解码器；
   tensorflow/chromium/ceph 都把 eigen/ffmpeg/rocksdb 以 `third_party` 形式拷进自己的树。
2. **同类不互为依赖**：libaom 与 libvpx、cryptopp 与 botan/nettle/mbedtls 都是平级，只有经验可复用。
3. **可选开关默认关**：opencv 的 `WITH_GDAL`、`BUILD_ZLIB` 在 Linux 下都不启用。

所以 `data/deps.csv` 里刻意纠正了初版 `plan.csv` 的伪依赖（原 `deps` 列把"同族"当成了"依赖"）：

| 原写法 | 改为 | 理由 |
|---|---|---|
| `x265 ← libde265` | soft | x265 自带解码器做分析，不链 libde265 |
| `libaom ← libvpx` | soft | 无编译依赖，只是 AV1/VP9 同族 |
| `eigen ← opencv` | soft（方向反过来：`opencv ← eigen` 也不成立，TF 自带 Eigen） | 上下游常被写反 |
| `ffmpeg ← flac/mpg123/SDL2` | soft | ffmpeg 有原生实现，外置只用于对照；SDL2 只影响 ffplay |

## 3. 层级（`layer` 写入 `data/plan.csv`）

`layer = 1 + max(layer(前置))`，只走 hard/bench：L0 无前置；L1 依赖已完成的 L0；L2 依赖 L1。

| 层 | 项目 |
|---|---|
| **L0** | 40 项：W1 六项 + libvpx/libaom/openh264/libwebp/opus/x264/x265/libde265/zimg/fftw/eigen/cryptopp/botan/nettle/mbedtls/tensorflow/hyperscan/...（自身无前置） |
| **L1** | libpng（←zlib-ng）、ffmpeg（←9 个 codec）、opencv（←jpeg/png/webp/ffmpeg）、node（←openssl）、pcl（←eigen）、kodi（←ffmpeg）、chromium（←zlib/png/jpeg/webp/vpx/ffmpeg/opus → 因 ffmpeg 在 L1 升为 L2） |
| **L2** | chromium、vlc（←ffmpeg） |

层级只有 3 层，说明"依赖"并不能把 48 项拉成一条长链——**能推后的只有 12 个链尾项目**，
其余 36 项仍需靠"优先级 + 每波预算"决定先后，否则会把 40 个 L0 全塞进 W2。

## 4. 新波次（`data/waves.csv`，构建顺序即波次顺序）

预算/波 = 剩余人日 / 剩余波次 = **494**，允许 5% 超出；波次是顺序阶段，
第 n 波天然依赖第 n-1 波，外加包级跨波依赖（表里 `deps` 列）。

| 波次 | deps | 项数 | 人日 | 项目（按层→优先级→工作量排序） |
|---|---|---|---|---|
| **W1** | — | 6 | 90 | pixman、openssl、libjpeg-turbo、zlib-ng、libgcrypt、libpng（**已全部 G2**） |
| **W2** | W1 | 6 | 515 | libvpx(184)、libaom(150)、openh264(86)、webrtc-ap(43)、libwebp(29)、opus(23) |
| **W3** | W2 | 10 | 515 | x264(115)、gromacs(92)、fftw(75)、cryptopp(46)、botan(37)、libde265(34)、ceph(32)、gdal(32)、zimg(29)、eigen(23) |
| **W4** | W3 | 7 | 512 | tensorflow(172)、x265(144)、hyperscan(132)、nettle(29)、mbedtls(14)、speexdsp(12)、flac(9) |
| **W5** | W1..W4 | 14 | 518 | node(103)、embree(92)、ffmpeg(69)、go(63)、john(46)、dlib(29)、SDL2(23)、pcl(23)、mpg123(12)、openal-soft(9)、pulseaudio(7)、rocksdb(7)、rust(3)、stockfish(32) |
| **W6** | W1,W2,W5 | 5 | 408 | chromium(259)、opencv(103)、kodi(32)、vlc(13)、libspeex(1，登记行) |

**每波的主题（用一句话就能说清，便于派工）**

- W1 快赢：上游已有 RVV，先把 A/B + 交叉 + CI 链路跑通（已完成）。
- W2 解码先于编码：视频/图像/语音**解码**内核 + 音频底座。位精确严格，但消费端必经。
- W3 编码与数学底座：x264/HEVC 软解、FFT/Eigen、密码库、存储/科学。
- W4 重编码与安全/搜索：x265、tensorflow（大头）、hyperscan、TLS 家族收尾。
- W5 集成前置：ffmpeg 把上面所有 codec 集成起来；node/pcl 各自的硬依赖已就绪。
- W6 平台集成：chromium / opencv / kodi / vlc——**它们消费前五波的全部成果**，放最后。

**优先级闸门**：W2/W3 只放 P0–P1，W4 放 P0–P2，W5/W6 全放。目的是让重活先落在
高优先级项目上，而不是"重量级波次里塞小项目凑数"。

## 5. 与初版顺序的差异（29 项变波次）

| 项目 | 初版 | 新 | 原因 |
|---|---|---|---|
| **ffmpeg** | W2 | **W5** | 9 条 bench 前置（vpx/aom/openh264/de265/x264/x265/zimg/opus/webp）全在后面，早做只能测到空开关 |
| **opencv** | W2 | **W6** | bench ← ffmpeg/libwebp；且它消费 jpeg/png/webp/ffmpeg 四家 |
| **chromium** | W6 | W6（内部顺序变最后） | 7 条 bench 前置，L2 |
| **vlc** | W6 | W6 | hard ← ffmpeg |
| **x264 / zimg / libde265** | W2 | **W3** | 编码/软解放在解码波之后 |
| **x265** | W2 | **W4** | 重编码，16×16 及以上块为主 |
| **opus / webrtc-ap** | W3 | **W2** | 无前置且是音频链路底座，提前 |
| **eigen / fftw / gromacs / gdal / ceph** | W5/W4 | **W3** | 无前置，早做能给 opencv/tensorflow/gromacs 复用 |
| **tensorflow** | W5 | **W4** | 自带 Eigen/FFT 拷贝，不阻塞 |
| **node** | W6 | **W5** | 唯一前置 openssl 已在 W1 |
| **rust / go / john / stockfish** | W6 | **W5** | 小项填缝，但只能进 W5 之后（闸门） |

**特意"不优化"的地方**：libvpx/libaom/openh264 三个解码大头留在 W2 同波并行——
它们互不依赖，串行只会拉长工期；板卡与评审才是瓶颈（见 §6）。

## 6. 重排后的排期（`data/ai-plan.csv`）

`scripts/ai-plan.py` 已改为读 `data/waves.csv`（缺文件时退回手工基线），
波次依赖由包级边自动推出，不再硬编码 `WAVES`。

| 波次 | 项目 | 起 | 止（末次评审） | 人日 |
|---|---|---|---|---|
| W1 | 6 | 2026-11-26 | 2026-12-01 | 90 |
| W2 | 6 | 2026-12-01 | 2027-01-04 | 515 |
| W3 | 10 | 2027-01-04 | 2027-02-04 | 515 |
| W4 | 7 | 2027-02-04 | 2027-03-08 | 512 |
| W5 | 14 | 2027-03-08 | 2027-04-06 | 518 |
| W6 | 5 | 2027-04-06 | 2027-05-07 | 408 |
| 合计 | 48 | 2026-11-26 | **2027-05-07（24.6 周）** | 2558 |

与初版 AI 排期（2026-11-16 → 2027-05-03，24.0 周）相比**多了 4 天**：把 codec 整体
提到 ffmpeg 之前，W2/W3 变得更"重"，评审队列多压了半周。**换来的收益是不做无效集成**：
按旧顺序，ffmpeg 在 W2 时 9 个 codec 一个都没完成，`--enable-libvpx` 之类的归因基准只能测到
上游空壳，等于白跑一轮。

敏感性（新波次重算）：

| 评审人 | 主线结束 | 结论 |
|---|---|---|
| 1 | 2027-09-20（44.0 周） | 单人评审 = 白等 4 个月 |
| **2** | **2027-05-07（24.6 周）** | 当前假设，无余量 |
| 3 | 2027-03-26（18.6 周） | 边际收益最大 |
| 4 | 2027-03-05（15.6 周） | 到串行下限 |

agent（1/3/4）与板卡（2/4/8）取不同值，结束日期**都不变**——瓶颈仍是评审席位。

## 7. 复现与维护（改顺序只改一处）

```bash
# 1) 只改依赖真值源
vim data/deps.csv            # 增删边；kind 必须是 hard/bench/soft，evidence 必填
# 2) 试算：不落盘，看层级与波次
python3 scripts/replan-waves.py --dry-run
# 3) 写回 plan.csv（wave/layer/deps 三列）+ 生成 waves.csv
python3 scripts/replan-waves.py
# 4) 重排期 → 看板 → 报表 → 一致性
python3 scripts/ai-plan.py --tps 60 --agents 8 --boards 8 --reviewers 2
python3 scripts/dashboard.py && python3 scripts/build-xlsx.py && ./scripts/verify.sh
```

**不要**直接手改 `plan.csv` 的 `wave`：`replan-waves.py` 会按依赖+预算+闸门覆盖，
手工改动在下次重排时会被抹掉。真值在 `deps.csv`，预算在 `--target`，闸门在脚本里。

## 8. 门禁增补：G1 必须证明"依赖真的被用上"

依赖重排后新增一条 G1 证据要求（写进 `docs/08-subagent-protocol.md` 的收工自查）：

- `configure` / `cmake` 的输出里，前置库必须**可见并启用**（如 ffmpeg 的
  `Enabled libvpx ... yes`、opencv 的 `JPEG: YES`）；
- 前置库的版本号与 `deps.csv` 的 evidence 一致；用系统库还是用 `-rvv` 版本，必须写清；
- 只声明"已链接"没有意义——**归因基准**里要把前置的贡献扣掉（bench 边的用途就是这个）。

## 9. 风险与未决

| 风险 / 未决 | 说明 | 处理 |
|---|---|---|
| bench 边的粒度偏保守 | ffmpeg 的 9 条 bench 把它压到 W5，但它**自身内核**（scale/colorspace/原生 H.264）不依赖任何 codec | 若 W4 有余量，允许把 ffmpeg 提前到 W4 插单，并在 `perf-log.md` 注明"外置 codec 归因基准延后到 W5" |
| `kodi ← ffmpeg` 从 soft 升为 bench | kodi 自带 ffmpeg 拷贝，编得过；但集成基准必须等 ffmpeg G4 | 已按 bench 处理，W6 |
| W6 只剩 408 人日 | 尾波不满预算，出现"评审已排满但项目已完"的空转 | 用 W5 的小项前移消化；不拆 chromium（259 人日不可拆） |
| 5 个上游 clone 未通（aom/x265/mpg123/pngquant/waypipe） | URL 未确认，`fetch-upstream.sh` 不能用 | 待用户确认；期间这几项只做骨架，不进 G1 |
| 依赖边会随上游版本漂移 | `DEPS`/`configure` 是快照事实 | 每次 rebase 后重跑 §7 的第 2 步，`diff` 依赖边 |
