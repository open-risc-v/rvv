---
name: rvv-port-project
description: 为 RISC-V RVV 移植计划新建一个「包名-rvv」工程骨架（模板取自 libspeex-rvv 的 A/B 工程范式），生成工具链、A/B 位精确门禁、内核差分、paired 基准、docs 与单工程迭代 Skill，并可挂到主仓库 projects/ 目录作为 git submodule。当用户要求“新建/初始化某个包的 RVV 移植工程”“给 libvpx/openssl/ffmpeg 之类包开工”“批量生出待开工工程骨架”“把移植工程挂成 submodule”时使用。
---

# 新建 RVV 移植工程

产出是**工程骨架**，不是移植代码：一条命令就能拿到"工具链 + A/B 门禁 + 内核差分 + 基准 +
文档 + 迭代手册"的可构建工程，然后才开 G1。模板抽象自 `libspeex-rvv`。

## 先确认三件事（缺就去问，不要猜）

1. **包名**（Gentoo atom，形如 `media-libs/libvpx`）；
2. **上游 git URL**——不确定就留空：`project.conf` 允许为空，`fetch-upstream.sh` 会拒绝执行；
3. **是否已有主仓库的 `data/plan.csv`**——有的话难度/优先级/波次/验证口径会自动带出，
   没有则按长尾（D2/P3/-）生成。

## 生成

**工程一律生成在主仓库的 `projects/` 下，且之后就在那里开发，不要在仓库外另建目录。**

```bash
# 主仓库里已有封装脚本：默认落到 <主仓库>/projects/<repo>，推荐用这条
<主仓库>/scripts/new-project.sh media-libs/libvpx

# 直接用生成器时，--dir 传「父目录」，所以要显式指向 projects/
python3 <此 Skill 目录>/scripts/new_project.py media-libs/libvpx \
  --dir <主仓库>/projects --upstream https://github.com/webmproject/libvpx

# 只看会生成什么，不落盘
python3 <此 Skill 目录>/scripts/new_project.py media-libs/libvpx --dry-run
```

已存在同名目录时默认拒绝，确认覆盖用 `--force`。字段覆盖用
`--upstream/--sha/--tag/--license/--priority/--wave/--difficulty/--path/--validation/--name`。

生成器会：复制 `assets/skeleton/`、替换 `{{...}}` 占位符、给 `.sh` 加可执行位、
处理 `.tmpl` 后缀、`git init` 并（本机已配 git 身份时）做首个 commit。**不下载源码。**

## 生成后按顺序做

1. **`./scripts/fetch-upstream.sh --dry-run`**：核对 URL/SHA。为空时不要自己补一个地址。
2. **`./scripts/fetch-upstream.sh`**：只把上游拉到 `baseline/`。再到 `src/` 建副本并提交
   （一次性提交，之后 `git diff` 才能看清哪些文件被动过）。
3. **`./scripts/build.sh riscv64`**：验证工具链。缺交叉工具链时用 `./scripts/docker-cross.sh`。
4. **`./scripts/native-baseline.sh`**：native A/B 也在 Linux 容器里跑（本机不编译），
   先让框架自检用例 PASS（这是 G1 的证据）。
5. **接入上游构建**：填 `cmake/upstream.cmake`，把 A/B 两侧都要用的二进制编出来。
   CMake / autotools / meson 三种做法见 `references/adapt-build-system.md`。
6. **写真实用例**：复制 `test/cases/00_framework.sh`，改成调用上游程序，产出确定性文件。
7. **接入主仓库**（在主仓库里）：`git add projects/<repo>` 把它登记成 gitlink 并提交；
   `projects/*/baseline/` 与 `projects/*/build/` 已在父仓 `.gitignore` 里，不会被误跟踪。
   再把该仓库推到 GitHub（见"推送与认证"一节）。
8. **更新状态**：`data/status.csv` 对应行改 `G1`，再跑 `python3 scripts/dashboard.py`。

## 工作位置（重要）

所有 28 个移植工程都在 `<主仓库>/projects/<pkg>-rvv`，**它们同时是 git 仓库和父仓的
submodule**。写代码、跑编译、改用例都直接在这个目录里做，不要再在 `~/work/` 下另建
`<pkg>-rvv` 副本——两套 checkout 会互相脱节，且主仓 `git status` 看不出指针落后。

`baseline/` 是上游快照（自身也是 git 仓库），不进父仓也不进子仓，删了可以用
`./scripts/fetch-upstream.sh` 重拉；`build/` 是构建产物，同理。

## 门禁与评审

G0→G5 的证据要求、评审提问、"假通过"清单见 `references/gates.md`。
一个工程最少要有：真实包用例的 `run_ab.sh` ALL PASS + 内核差分全绿 + 三轮成对性能数字。

## 内核迭代

骨架自带工程内 Skill `skills/rvv-kernel-loop/SKILL.md`，规定"每轮只动一个内核"的七步顺序
与失配/性能排查顺序。开工后按它推进，不要另起流程。

## 目录与字段规格

`project.conf` 每个字段的含义、命名规则（`libsdl2 → SDL2-rvv`、`crypto++ → cryptopp-rvv`、
`-compat` 不立项等）、与主仓库的关系见 `references/project-spec.md`。

## 骨架包含什么

```
CMakeLists.txt / CMakePresets.json   native、riscv64、riscv64-x100、riscv64-baseline 四个 preset
cmake/toolchain-riscv64-linux.cmake  双发行版 sysroot 探测 + qemu 作为 CTest 模拟器
cmake/upstream.cmake                上游接入点（G1 填）
test/run_ab.sh                      A/B 逐字节门禁（用例在 test/cases/）
test/rvv_diff.{h,c}                 内核差分框架（长度×种子×越界哨兵）
test/diff_kernels.c                 登记表 + 两个可直接跑通的示例内核
test/cpu_probe.c                    VLEN/v_intrinsic + vle/vlse/vrgather/vsetvl 微基准
benchmark/pair_bench.sh             A/B 交替 REPS 次取中位，输出比值
scripts/{build,docker-cross,device-test,fetch-upstream}.sh + Dockerfile.buildenv
docs/{plan,rvv-notes,perf-log,progress,final-report}.md
skills/rvv-kernel-loop/SKILL.md     单工程七步循环
```

## 容易踩的坑

- **不要替用户猜上游 URL**。包名对上不代表仓库地址对（`x265` 在 `code.videolan.org`，
  `waypipe` 在 `gitlab.freedesktop.org`）；留空比填错好。
- **`--dir` 是父目录**，不是工程目录本身。
- **不要先下载源码**。骨架阶段只需要 URL；`fetch-upstream.sh` 是显式、可审的动作。
- **不要在 `baseline/` 里改任何东西**。它是 A/B 的唯一参照，改了就全部作废。
- **A/B 只能差一个变量**：`RVV_KERNELS`。一侧 `-O2` 一侧 `-O3` 会让结论失效。
- **用例必须产出文件**。两个空目录 `diff -r` 也"一致"，框架用"产出数为 0 判 FAIL"挡住，
  自己写用例时同样要自证。
- **shell 里中文紧贴变量名会解析错**（macOS bash 3.2 会把多字节字符当成变量名的一部分），
  写成 `${VAR}中文`。骨架已按此规则写，改脚本时保持。
- **qemu 数字不能当性能结论**，只能证明功能正确。
- **不要在宿主（macOS）上编任何东西**：native 与 riscv 都用容器，否则宿主特有的链接问题
  （如 macOS 缺 CoreFoundation）会污染基线。
- **上游 submodule 要单独 init**：`fetch-upstream.sh` 只克隆主仓，`graphengine` 之类的子模块是空目录。
- **浮点包别用"逐字节"当判据**：量化后再取哈希，误差单独对 long double 参考打印。
- **C++ 库 + C 探针别写 `-lstdc++`**：交叉 sysroot 只有 `libstdc++.so.6`，用 `LINKER_LANGUAGE CXX`。
- **`run_ab.sh` 里执行用例必须用 `bash`**：Ubuntu 的 `sh` 是 dash，`set -o pipefail` 直接失败，
  所有用例变 SKIP、最后打印 "ALL PASS（0 个用例）"，是假绿。
