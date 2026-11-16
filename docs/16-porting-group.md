# 移植项目组（RVV Porting Group）

一个**中心仓库 + 每包一个子仓库**的组织形态：中心仓库管立项、排序、门禁、汇总；
每个包一个独立工程仓库，互不阻塞，可并行推进、可单独被外部引用。

- 组织位置：GitHub `open-risc-v`
- 中心仓库（计划项目）：[`rvv`](https://github.com/open-risc-v/rvv)
- 子项目：22 个，全部以 **git submodule** 挂在 `projects/` 下，`.gitmodules` 使用 GitHub 绝对地址，
  因此 `git clone --recursive` 即可拿到完整项目组。

## 仓库状态（2026-11-16）

24 个仓库**全部 public**，中心仓库与 22 个子仓库的远端提交与本地一致，`git clone --recursive`
已从空目录实测通过（22 个子模块指针均可检出）。

| 仓库 | 说明 |
|---|---|
| [`rvv`](https://github.com/open-risc-v/rvv) | 中心仓库（计划、门禁、状态、报告） |
| 22 个 `*-rvv` | 挂在 `projects/` 下的子工程，见下方全量表 |
| [`libspeex-rvv`](https://github.com/open-risc-v/libspeex-rvv) | 模板来源工程，单独公开但不作为 submodule（不属 48 项计划） |

复现：

```bash
git clone --recursive https://github.com/open-risc-v/rvv.git
cd rvv && git submodule status     # 22 行，指针即验收版本
```

提交前已做脱敏：真机地址与口令替换为 `<BOARD_HOST>` / `<BOARD_PASS>`，本地绝对路径
替换为 `~/work/`，内部工作区路径替换为 `<internal-workspace>`；10 个仓库重写历史后再推。
openssl 仓库内 `test/*.pem` 的测试私钥与上游逐字节一致（官方自带样例），未做改动。

## 关联关系

```
rvv（计划/门禁/汇总）
└── projects/<pkg>-rvv   →  submodule → https://github.com/open-risc-v/<pkg>-rvv.git
```

- **指针即版本**：中心仓库里记录的 submodule 提交就是该子项目"被验收过的版本"；
  子项目继续往前推不会自动影响中心仓库，需要显式 `git add projects/<pkg>` 更新指针。
- **一个包一个仓库**：子仓库自带 `baseline/`（上游只读参照）+ `src/`（移植副本）+ `test/` +
  证据文档，可独立构建、独立复核。上游 SHA 固定在 `project.conf`。

## 门禁（每个子项目独立判定）

| 门 | 含义 | 最小证据 |
|---|---|---|
| G0 | planned | 立项：上游 SHA 固定、难度/优先级落表 |
| G1 | buildable | native 构建 + 框架自检 `run_ab.sh` PASS |
| G2 | baseline | native A/B 位精确 + riscv64 交叉基线（qemu 功能一致） |
| G3 | rvv-kernel | 对标 SSE/NEON 的内核已实现；qemu 逐字节一致 + 真机 A/B 有数字 |
| G4 | integrated | 接入真实编解码/渲染路径，整链收益有数字 |
| G5 | upstreamed | 上游接收 |

## 子项目一览

| 计划 ID | 包 | 子仓库 | 波次 | 优先级 | 难度 | 门禁 | 最新证据 |
|---|---|---|---|---|---|---|---|
| RVV-026 | `dev-libs/botan` | [botan-rvv](https://github.com/open-risc-v/botan-rvv) | W3 | P1 | D3 | **G2** | botan-rvv/docs/evidence/G2-baseline-20261113.md |
| RVV-028 | `sys-cluster/ceph` | [ceph-rvv](https://github.com/open-risc-v/ceph-rvv) | W3 | P1 | D3 | **G1** | 骨架就位；源码未拉（体量大，需专用镜像与依赖） |
| RVV-027 | `dev-libs/crypto++` | [cryptopp-rvv](https://github.com/open-risc-v/cryptopp-rvv) | W3 | P1 | D3 | **G2** | cryptopp-rvv/docs/evidence/G2-baseline-20261113.md |
| RVV-032 | `dev-cpp/eigen` | [eigen-rvv](https://github.com/open-risc-v/eigen-rvv) | W3 | P1 | D4 | **G2** | eigen-rvv/docs/evidence/G2-baseline-20261113.md；自带 RVV10 后端但需 GCC 14（见 docs/15 §2） |
| RVV-033 | `sci-libs/fftw` | [fftw-rvv](https://github.com/open-risc-v/fftw-rvv) | W3 | P1 | D5 | **G2** | fftw-rvv/docs/evidence/G2-baseline-20261113.md |
| RVV-034 | `sci-libs/gdal` | [gdal-rvv](https://github.com/open-risc-v/gdal-rvv) | W3 | P1 | D3 | **G1** | 骨架就位；源码未拉（依赖 GDAL 全家桶，需先定最小配置） |
| RVV-035 | `sci-chemistry/gromacs` | [gromacs-rvv](https://github.com/open-risc-v/gromacs-rvv) | W3 | P1 | D5 | **G2** | gromacs-rvv/docs/evidence/G2-baseline-20261113.md |
| RVV-012 | `media-libs/libaom` | [libaom-rvv](https://github.com/open-risc-v/libaom-rvv) | W2 | P1 | D5 | **G3** | libaom-rvv/docs/evidence/G3-kernel-20261114.md |
| RVV-015 | `media-libs/libde265` | [libde265-rvv](https://github.com/open-risc-v/libde265-rvv) | W3 | P1 | D3 | **G3** | libde265-rvv/docs/evidence/G3-kernel-idct8-20261115.md |
| RVV-006 | `dev-libs/libgcrypt` | [libgcrypt-rvv](https://github.com/open-risc-v/libgcrypt-rvv) | W1 | P1 | D4 | **G3** | libgcrypt-rvv/docs/evidence/G3-kernel-20261114.md |
| RVV-001 | `media-libs/libjpeg-turbo` | [libjpeg-turbo-rvv](https://github.com/open-risc-v/libjpeg-turbo-rvv) | W1 | P0 | D3 | **G3** | libjpeg-turbo-rvv/docs/evidence/G3-kernel-20261114.md |
| RVV-003 | `media-libs/libpng` | [libpng-rvv](https://github.com/open-risc-v/libpng-rvv) | W1 | P0 | D2 | **G3** | libpng-rvv/docs/evidence/G3-kernel-20261114.md |
| RVV-009 | `media-libs/libvpx` | [libvpx-rvv](https://github.com/open-risc-v/libvpx-rvv) | W2 | P0 | D5 | **G3** | libvpx-rvv/docs/evidence/G3-kernel-sad-20261115.md + G3-kernel-sse-20261116.md |
| RVV-008 | `media-libs/libwebp` | [libwebp-rvv](https://github.com/open-risc-v/libwebp-rvv) | W2 | P0 | D3 | **G3** | libwebp-rvv/docs/evidence/G3-kernel-sse-20261115.md |
| RVV-010 | `media-libs/openh264` | [openh264-rvv](https://github.com/open-risc-v/openh264-rvv) | W2 | P0 | D4 | **G3** | openh264-rvv/docs/evidence/G3-kernel-sad-20261115.md |
| RVV-005 | `dev-libs/openssl` | [openssl-rvv](https://github.com/open-risc-v/openssl-rvv) | W1 | P0 | D4 | **G3** | openssl-rvv/docs/evidence/G3-asm-zvk-20261116.md（上游自带 Zvkned/Zvknha 汇编；真机 CBC 138×/143×、CTR 284×、SHA-256 8.5×） |
| RVV-017 | `media-libs/opus` | [opus-rvv](https://github.com/open-risc-v/opus-rvv) | W2 | P0 | D3 | **G3** | opus-rvv/docs/evidence/G3-kernel-xcorr-20261115.md |
| RVV-002 | `x11-libs/pixman` | [pixman-rvv](https://github.com/open-risc-v/pixman-rvv) | W1 | P0 | D4 | **G3** | pixman-rvv/docs/evidence/G3-kernel-20261114.md |
| RVV-018 | `media-libs/webrtc-audio-processing` | [webrtc-ap-rvv](https://github.com/open-risc-v/webrtc-ap-rvv) | W2 | P0 | D3 | **G2** | webrtc-ap-rvv/docs/evidence/G1-native-build-20261113.md + docs/12-w2-baseline.md |
| RVV-013 | `media-libs/x264` | [x264-rvv](https://github.com/open-risc-v/x264-rvv) | W3 | P1 | D5 | **G3** | x264-rvv/docs/evidence/G3-kernel-sad-20261115.md |
| RVV-014 | `media-libs/zimg` | [zimg-rvv](https://github.com/open-risc-v/zimg-rvv) | W3 | P1 | D3 | **G3** | zimg-rvv/docs/evidence/G3-kernel-resize-{v,h}-20261116.md（垂直 7.57×、水平 2.67×、整链 4.24×） |
| RVV-004 | `sys-libs/zlib-ng` | [zlib-ng-rvv](https://github.com/open-risc-v/zlib-ng-rvv) | W1 | P0 | D2 | **G3** | zlib-ng-rvv/docs/evidence/G3-kernel-20261114.md |

## 度量口径（所有子项目统一）

- **A/B 只差一个变量**：`RVV_KERNELS`（或等价的编译开关），两侧同 `-march`、同优化级别。
- **功能**：qemu 下逐字节一致；浮点内核相对误差 ≤ 1e-6。
- **性能**：只在真机取（qemu 计时噪声大于信号，不可用）。每侧 5 轮交替、每轮内侧 3 次取最优。
- **归因**：内核加速比与整链加速比分开报；整链收益必须能用"该内核耗时占比 × 内核加速比"解释。
- **构建**：全部在 Linux 容器内交叉编译（`riscv64-linux-gnu-gcc` + sysroot `/usr/riscv64-linux-gnu`）。

## 新增一个子项目

用 Skill `rvv-port-project` 生成骨架 → 拉上游到 `baseline/` → 提交 `src/` 快照 →
在中心仓库 `./scripts/add-submodule.sh <pkg>` 挂载 → 回填 `data/status.csv`。
