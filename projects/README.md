# projects/ —— 移植工程子模块

每个在册移植工程是 **一个独立 git 仓库**，以 submodule 形式挂在 `projects/<short>-rvv/`。
本目录不放源码副本，只放指针（`.gitmodules` + gitlink）。

## 1. 命名规则

| 情况 | 仓库名 | 例子 |
|---|---|---|
| 常规 | `<short>-rvv` | `libvpx-rvv`、`ffmpeg-rvv` |
| short 有歧义 | `<shell>-<short>-rvv` | `libsdl2` → `SDL2-rvv`；`openssl-compat` 不立项 |
| 已完成样本 | 保持原名 | `libspeex-rvv`（在 `../libspeex-rvv`，不复制） |

`short` = Gentoo atom 的最后一段，去掉 `-compat`、`-1.14.0` 这类后缀。

## 2. 注册流程

```bash
# ① 生成骨架（不下载源码，只建结构 + 工具链 + A/B 框架）
../scripts/new-project.sh media-libs/libvpx

# ② 挂为子模块（默认取同级目录 ../libvpx-rvv）
../scripts/add-submodule.sh media-libs/libvpx

# ③ 需要时才拉源码（先 clone 上游到 baseline/，再同步到 src/）
../scripts/sync.sh libvpx
```

三条约定：

1. **`new-project.sh` 绝不下载源码**。它只复制模板骨架、替换包名/上游/LICENSE，并生成
   `project.conf`。源码拉取是 `sync.sh` 的显式动作，且需要人确认上游 URL 与 SHA。
2. **子模块 URL 优先用相对路径**（`../libvpx-rvv`），便于本地并行开发；镜像到远端后
   再由 `.gitmodules` 统一改为 `https://...` 并批量 `git submodule sync`。
3. **`projects/` 下不放任何未注册的目录**。`scripts/verify.sh` 会检查目录集合与
   `.gitmodules` 的一致性，不一致时 CI 失败。

## 3. 每个工程的内部结构（与 `../libspeex-rvv` 对齐）

```
<short>-rvv/
├── baseline/            上游只读快照（git submodule 或浅克隆，打 tag 记录 SHA）
├── src/                 移植工作副本（RVV 内核在 src/<lib>/rvv/）
├── test/                run_ab.sh（A/B 逐字节）、*_diff.c（内核差分）、cpu_probe.c
├── benchmark/           bench_e2e（端到端）、bench_kernel（单内核）
├── cmake/               toolchain-riscv64-linux.cmake、config.h.in
├── scripts/            build.sh、docker-cross.sh、device-test.sh、Dockerfile.buildenv
├── docs/                plan.md（范围与通过标准）、rvv-notes.md（坑）、perf-log.md、progress.md
├── skills/rvv-kernel-loop/SKILL.md
├── project.conf         机器可读元数据（包名、上游、SHA、口径、优先级）
└── CMakeLists.txt / CMakePresets.json
```

`project.conf` 是本仓库 `data/status.csv` 与看板的唯一自动数据源，字段见
`.user_skills/rvv-port-project/references/project-spec.md`。

## 4. 与主仓库的关系

- 主仓库（`rvv/`）**不构建任何子项目**，只做：清单、计划、状态、看板、模板、Skill。
- 子项目**不依赖主仓库**，可以单独 clone / 单独 CI；主仓库只是索引。
- 因此：不要把公共 CMake 代码放进主仓库；要放就放进 Skill 的 `assets/skeleton/`。

## 5. 已在册的工程

| 包 | 工程 | 门禁 | 说明 |
|---|---|---|---|
| `media-libs/libjpeg-turbo` | `projects/libjpeg-turbo-rvv` | G0 | 骨架来自 Skill，本机 A/B 框架自检 PASS；上游 URL 已确认 |

## 6. 子模块的日常操作

```bash
# 子工程推进后，主仓库要同步指针（否则 verify 会看到旧 commit）
git -C projects/libjpeg-turbo-rvv pull --ff-only
git add projects/libjpeg-turbo-rvv && git commit -m "submodule: bump libjpeg-turbo-rvv"

# 新环境克隆主仓库（先把子模块一起拉下来）
git clone --recurse-submodules <rvv 仓库>
```

本地同级工程用相对路径（`../<repo>`）作 URL 时，git 默认禁止 file 传输；
`scripts/add-submodule.sh` 只对本地路径加 `-c protocol.file.allow=always`，远端地址不受影响。

