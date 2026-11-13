# 03 RVV 移植技术路线

## 0. 先分类，再动手

任何包进来，第一件事不是写内核，是判定它属于哪条路径。**路径决定工作量结构与验证方式**，
判错路径是最贵的错误（把汇编包当 intrinsics 包估，会低估 3 倍以上）。

```
上游有 RVV 内核？ ── 是 ──> 路径 A 集成 + 缺口 + 调优
        │
        否
        ↓
核心路径是手写汇编（.asm/.S）？ ── 是 ──> 路径 C 语义复原
        │
        否
        ↓
需要改数据布局/算法骨架？ ── 是 ──> 路径 D 架构级重构
        │
        否
        ↓
路径 B 按 C intrinsics 参照重写（有 NEON/SSE C 版最好，没有就按标量语义）
```

## 1. 路径 A：集成 + 缺口 + 调优（最高 ROI）

适用：上游已有 RVV 实现的包（`libjpeg-turbo`、`libpng`、`zlib-ng`、`pixman`、`openssl`、
`libgcrypt`、`ffmpeg`、`eigen`、`vlc`、`ceph`）。

1. **核实而非相信**：读上游 `arch/riscv` 或 `simd/riscv64` 目录，列出"已覆盖内核清单"，
   与 x86/NEON 侧清单做差集 → 缺口表进 `docs/plan.md`。
2. **确认版本轴**：RVV 代码通常挂 `__riscv_v_intrinsic >= 12000` 或 `zvl*`/`vlen` 假设。
   目标机是 RVV 1.0、VLEN=256，需确认上游是否偷偷假设了 VLEN=128（`-mrvv-vector-bits`）。
3. **补 dispatch**：多数包有运行期分派（`cpuid`/`hwcap`/`__riscv_hwprobe`）。确认在
   非 RVV 目标机上不会执行向量指令（安全回退）。
4. **做 A/B**：用上游自带 CLI（如 `cjpeg/djpeg`、`pngtest`、`zlib-ng-test`）产生黄金数据，
   bit-exact 比对；再上真机 paired 基准。
5. **只补缺口，不重写**：这条路径的纪律是**不要动机上已经有的内核**——重写会引入
   bit-exact 风险且没有收益。

**常见坑**：上游 RVV 实现往往只在特定 VLEN 上测过；`vlseg`/`vrgather` 在 VLEN=512 上
性能形态可能反转。必须按 `docs/05-waves.md` 的 VLEN 矩阵回归。

## 2. 路径 B：按参照重写（主力工作量）

适用：有 NEON/SSE **C intrinsics** 版本，或只有标量 C 但有清晰热点。

1. **先定"内核契约"**：每个内核写清输入输出、边界（长度是否总是 4/8/16 的倍数）、
   溢出/舍入/饱和语义、是否允许改变累加顺序。契约写不出来 = 不能开工。
2. **用 C 先写一遍语义版**（不向量化），与标量实现做差分，确保理解正确。
3. **再向量化**，按下面的形状优先级：
   - 逐元素（map）：最便宜，`vle/vse` + 一次运算；
   - 点积/归约（reduce）：**不要每 entry 做一次 `vredsum`**（`libspeex-rvv` 第 1 轮教训：
     直接打平 gcc auto-vec）。改为 entry 并行：一 lane 一个 entry，标量广播 + `vwmacc`，
     最后一次性归约；
   - 跨 lane（shuffle/pack）：最贵，先想办法用"数据布局换指令"绕开（转置一次，换 N 次便宜加载）。
4. **误差可控的才用宽运算**：定点路径不要用 `vnclip`（受 `vxrm` 影响），用 `vsra + vncvt`
   精确复现截断；浮点路径先确认用不用 FMA（FMA 会改变舍入）。
5. **每个内核一个差分测试**（见 `docs/06-acceptance.md`），随机 + 极值 + 长度边界。

## 3. 路径 C：汇编语义复原

适用：x264/x265、libvpx、openh264、nettle、crypto++ 这类"核心路径全是汇编"的包。

1. **先算收益，再决定范围**：不是所有汇编都值得搬。用剖析确定热点，只对
   "top-N 内核 + 覆盖 ≥60% 时间"的集合做复原，其余保持标量。
2. **三份材料对照**：汇编实现、上游 C 参考实现、以及该算法的规范/论文。
   只用汇编当参照会继承它的历史 bug 与隐式前提（对齐、越界读、临时缓冲）。
3. **逐内核"语义等价证明"**：写清"汇编里的饱和/移位/打包顺序"如何映射到 RVV，
   写出等价性论证放进 `docs/rvv-notes.md`（这是 bit-exact 争议时的唯一依据）。
4. **优先 C intrinsics，不写 `.S`**：RVV 的编译器内建已能生成可接受代码；
   只有在需要手工调度（长向量链、寄存器压力）时才落到 `.S`，并保留 C 版做对照。
5. **位精确回归用上游自己的 checkasm/fate**：`ffmpeg` 有 `checkasm`，`libvpx` 有
   `test/` 向量测试，`x264` 有 `checkasm`。**自建 A/B 不能替代上游回归集**。

## 4. 路径 D：架构级重构

适用：`fftw`、`eigen`（调优）、`tensorflow`/XNNPACK、`hyperscan`、`embree`、`gromacs`。

这类包的特征是"SIMD 不是点缀，是算法的一部分"：寄存器宽度进入分块参数、数据布局按
x86 lane 数设计、尾块处理写死。

1. **先做参数化**：把 `4/8/16` 这类硬编码 lane 数提升为编译期常量（`RVV_LANES` 由
   `vsetvlmax` 推导），这一步不做，后面全是补丁摞补丁。
2. **再选骨架**：GEMM 的 blocking、FFT 的 codelet 分解、正则的匹配自动机、
   BVH 的遍历顺序，必须在 RVV 的"向量长度可变"前提下重新选一遍。
3. **VLEN 无关是硬约束**：禁止 `zvl*` 定长编译；所有循环 `vsetvl` 驱动；
   尾块用 strip-mining，不用掩码补零假装。
4. **收敛判据前置**：开工就写明"到什么程度停"（例如 GEMM 达到同频 AVX2 的 70%、
   FFT 达到 FFTW 自身 SSE 版的 60%），否则会无边界投入。

## 5. 公共基建（W0 一次做完，所有包复用）

### 5.1 工具链矩阵

| 项 | 选型 | 说明 |
|---|---|---|
| 编译器 | gcc 14.2 交叉（生产）、gcc 15 / clang 18（对照） | `libspeex-rvv` 实测 gcc-14 优于厂商 gcc-15；编译器只认同机配对测量 |
| `-march` | `rv64gcv`（基线）/ `+zba_zbb_zbc_zbs_zicond`（X100）/ `+zvbb_zvbc_zvkned`（密码类） | 语义无风险的扩展才纳入默认 |
| 禁止 | `-mrvv-vector-bits=zvl*`、`-mtune=<厂商近似>` | 前者破坏 VLEN 无关，后者实测回退 |
| 内建 API | `__riscv_v_intrinsic` 版本轴（`rvv_arch.h` 集中门控） | 兼容 v0.11/v1.0 两代 |

### 5.2 分派与门控

```c
/* 所有工程统一的形态：编译期能力 + 运行期探测 + 安全回退 */
#if defined(__riscv_v_intrinsic) && (__riscv_v_intrinsic >= 12000)
#  define PKG_HAVE_RVV 1
#endif
/* 运行期：__riscv_hwprobe(V_EXT) 或 /proc/cpuinfo；探测失败一律回退标量 */
```

### 5.3 验证与基准

- `test/ab_run.sh`：同选项构建 A（`src/`）与 B（`baseline/`），跑 `test/ab_spec.sh` 里的
  命令序列，逐字节/逐数值比对，含交叉解码（编解码类必做）。
- `test/diff_*.c`：内核级差分，注册进 CTest，qemu + 真机双跑。
- `test/cpu_probe.c`：VLEN、`vsetvl` 开销、`vlse` vs `vle` 比值、`vmacc` 吞吐、标量/向量比。
  **每个新目标机先跑 probe，再谈优化**。
- `scripts/paired-bench.sh`：A/B 交替 ≥5 对取中位；分母是同选项 `RVV_KERNELS=OFF`。
- 毒化矩阵：`qemu -cpu rv64,v=true,vlen={128,256,512},vext_spec=v1.0` ×
  {normal, ta_all_1s, ma_all_1s, ta+ma}，用于抓"尾部 agnostic"错误。

### 5.4 尾部与掩码纪律（从 `libspeex-rvv` 直接继承）

1. 短 VL 写操作的目的地尾部是 indeterminate：**跨操作读取尾部 = 源码 bug**。
   持久累加器一律 `_tu` 后缀更新。
2. `vsetvl` 必须是循环体第一句，先于任何使用 `vl` 的语句（否则 `n -= vl` 死循环）。
3. `vmerge` 的操作数序（gcc 与规范相反）、`vredsum/vredmax` 的 (vector, carrier) 序，
   用已知值单测固定下来，写注释。
4. 掩码类型是 `vbool(SEW/LMUL)`，不是"每元素 1 bit"。
5. `vlse` 的 stride 单位是**字节**；`vlseg` 段加载只在 gcc-14+ 可用，且要用
   "field k == 第 k 路 stride 加载"来证明位精确。
6. 累加顺序改变会改变结果：多 lane 累加后必须按标量顺序归约，或证明运算满足
   结合律（如 `mod 2^32` 加法）。

## 6. 一个包从立项到收敛的标准动作

| 步 | 动作 | 产物 |
|---|---|---|
| 1 | 判路径（A/B/C/D）、定契约、定验收口径 | `docs/plan.md` 首段 |
| 2 | 骨架 + baseline 快照 + 构建 | G1 |
| 3 | A/B 工具跑通，先测未优化版基线 | G2 + `perf-log` 基线表 |
| 4 | probe + 剖析，热点排序 | `plan.md` 内核优先级表 |
| 5 | 逐内核落地 + 差分测试 + 真机 A/B | G3，`perf-log` 逐轮 |
| 6 | 覆盖度反推，判定收敛 | G4 |
| 7 | 上游化（PR 或维护分支） | G5 |

**禁止跳步**：没有 G2 的基线就直接优化，最后无法给出可信加速比——这是本工程最常见的返工原因。

## 构建环境：一律 Linux 容器，宿主只当编辑器

从 W1/W2 的 12 个包起，**任何编译（native A/B 与 riscv64 交叉）都在 Linux 容器里做**，
macOS 宿主不参与编译。理由不是偏好，是三个已实际踩到的问题：

1. 宿主特有的链接问题会伪装成移植问题。`webrtc-audio-processing` 的 upstream `examples`
   在 macOS 上缺 CoreFoundation 符号，换 Linux 后完全消失，不必给上游打补丁。
2. native 与 riscv 必须同 glibc、同编译器版本，否则两侧差异分不清是架构还是 C 库。
3. 依赖库的同版本供给更容易：容器里可以烤进指定版本的 zlib / libgpg-error（宿主 brew 版本不可控）。

| 镜像 | 内容 | 用途 |
|---|---|---|
| `rvv-cross:1` | Ubuntu 24.04 + riscv gcc 13.3 + qemu + cmake/ninja/meson/autotools | CMake/meson/autotools 上游交叉编 |
| `rvv-cross:2` | `rvv-cross:1` + `g++-riscv64-linux-gnu` | 探针是 C++ 或上游含 C++（libvpx/libaom/openh264/webrtc-ap） |
| `rvv-cross-gperr:3` | 上述 + riscv 版 gpg-error 1.61（`/opt/gpg-error`）+ `gpg-error-config` shim | libgcrypt 交叉 |
| `rvv-build:1` | `rvv-cross:2` + zlib1g-dev + native gpg-error 1.61（`/opt/gpg-error-native`） | native 侧需要 zlib / gpg-error |
| `rvv-build:2` | `rvv-build:1` + `gpg-error-config` shim | libgcrypt native A/B |

工程侧约定（骨架已带）：

- `./scripts/native-baseline.sh` —— 把 `./test/run_ab.sh` 丢进容器跑 native A/B；
- `./scripts/cross-baseline.sh` —— 容器内编 riscv64 + `qemu-riscv64 -L /usr/riscv64-linux-gnu` 跑探针。

两个必须遵守的细节：`run_ab.sh` 执行用例要用 `bash`（Ubuntu 的 `/bin/sh` 是 dash，
`set -o pipefail` 会失败并把用例全算成 SKIP，最后打印 "ALL PASS（0 个用例）" 的假绿）；
两侧的依赖提供方要一致（如 libpng 必须两侧都用 zlib-ng，否则码流字节天然不同）。
