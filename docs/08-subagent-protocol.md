# 08 sub-agent 派工协议

> 目的：把 48 个工程拆给多个 sub-agent 并行推进，同时让每个 agent 的**输入、输出、边界、
> 验收**都是确定的——不靠人反复叮嘱，也不靠 agent 自己"领会"。

## 1. 为什么是一个工程一个 agent

- 单工程的上下文（上游布局、构建方式、内核语义、踩过的坑）**无法跨工程复用**；
- 每换一次会话，重建上下文要 50–150k token（见 `docs/07` §9）；
- 一个 agent 同时抓两个工程，两边都会把"改 baseline 图省事"当成正常操作。

所以：**一个工程 = 一个 agent = 一个会话，从 G2 干到 G4**，中间不换人。

## 2. 三个角色

| 角色 | 谁 | 干什么 | 不干什么 |
|---|---|---|---|
| 派工方 | 主 Agent（我） | 生成工作单、分配 agent/板卡槽位、跑验收、回写 `data/status.csv`、裁决"要不要改上游语义" | 不替 sub-agent 写代码，不改它的 `src/` |
| 执行方 | 每工程 1 个 sub agent | 按工作单推进 G2→G3→G4，交证据包 | 不动 `baseline/`、不动主仓库 `data/`、不跨工程 |
| 评审方 | 人（1–3 人） | 按 `references/gates.md` 看证据、拍 G2/G4 通过 | 不做逐行 code review（那是 agent 的活） |

## 3. 启动包（派工时必须原样给出）

每个 sub-agent 的第一条消息 = **工作单路径 + 四条硬约束**，其余让它自己读：

```
你的任务：按 ~/work/rvv/data/workorders/RVV-002-pixman.md 推进 pixman-rvv。

- 工程目录：~/work/pixman-rvv（baseline 已固定在上游 3174212a，src 已快照同样内容）
- 必读 Skill：~/work/pixman-rvv/skills/rvv-kernel-loop/SKILL.md（每轮七步，不许自创流程）
- 硬约束：① 不改 baseline/；② A/B 只允许差 RVV_KERNELS；③ 不猜上游 URL/SHA，需要换固定点先报我；
         ④ 每轮结束 quote 出 run_ab.sh 与 diff_kernels 的真实输出，不许转述。
- 交付：工程内 git commit（前缀 G2:/G3:/G4:）+ docs/evidence/G{2,3,4}-<日期>.md + 一段回报
        （当前门禁 / 跑过的命令 / A/B 与比值 / 未完成项 / 需要我拍板的问题）。
```

要点：**路径全给绝对路径**。sub-agent 不继承本会话的 skill 目录清单，也不会自己去找模板。

## 4. 资源槽位（来自 `data/ai-plan.csv`）

| 资源 | 数量 | 规则 |
|---|---|---|
| agent | 3–4（建议 4） | 一个 agent 独占一个工程到评审完；不要为了"看起来快"开到 8 |
| 板卡 | 2–4 | 验证期独占；同一块板不并行跑两个工程的 A/B（频率/温度互相污染） |
| 评审队列 | 1 条（2–3 人） | 按项目排，不按波次排；小项目攒批走"快审窗口" |

首个工程的槽位在 `ai-plan.csv` 里已经写死（`agent` / `board` 两列），照抄。

## 5. 回收验收（派工方每条都要跑，不看 agent 的自述）

```bash
cd <工程目录>
./test/run_ab.sh                     # ALL PASS 且用例数 ≥1、产出数 >0
./build/riscv64/diff_kernels         # 0 FAIL（差分覆盖 VL 边界与非 2 的幂）
git status --porcelain              # 空：所有改动都已提交
git log --oneline -3                # 提交粒度对得上工作单的阶段
```

有一条不过就退回，不进入下一门禁。

## 6. 失败升级（不要让 agent 自己硬扛）

| 现象 | 处理 |
|---|---|
| 同一内核差分连续 2 轮失配 | 停手，写"假设 + 反证实验"进 `docs/rvv-notes.md`，报派工方 |
| 性能不升反降 | 先查 `vlse` vs `vle`、`vsetvl` 位置、尾部 agnostic（`docs/04` 已列） |
| 上游构建接不进来 | 回 `references/adapt-build-system.md`，仍不行就改用路径 C（绕过构建，直接测内核） |
| 需要改上游语义才能对齐 | **禁止自行决定**，报派工方；这属于验收口径变更 |
| 上游 SHA 拿不到 / 仓库要 auth | 停，报派工方（如 `aom` `x265` `waypipe` 这类） |

## 7. 状态回写由派工方做

sub-agent **不写** `data/status.csv`、不改 `STATUS.md`、不动主仓库。流程是：
agent 回报 → 派工方跑验收 → 通过则 `gate` 升一级 + 写 `evidence` 串 → `python3 scripts/dashboard.py`。

## 8. 当前进度

| 工程 | 门禁 | 上游固定点 | 上游构建系统 | 真实用例 | 证据 |
|---|---|---|---|---|---|
| `pixman-rvv` | **G2** | `3174212a` | meson | fill + OVER 合成 + 线性渐变 | `docs/evidence/G2-20261113.md` |
| `libjpeg-turbo-rvv` | **G2** | `3ef3367e` | cmake | 编码→解码回环（q85/ISLOW） | 同上 |
| `libpng-rvv` | **G2** | `7ef5852d` | cmake | 全过滤类型编码→解码回环 | 同上 |
| `zlib-ng-rvv` | **G2** | `6727d883` | cmake | deflate/inflate 回环 | 同上 |
| `openssl-rvv` | **G2** | `3f11738c` | perl Configure | AES-128-CBC + SHA-256 | 同上 |
| `libgcrypt-rvv` | **G2** | `88563e87` | autotools | SHA-256 + AES-128-CBC | 同上 |

六项都已 `run_ab.sh` **ALL PASS（2 个用例）**。下一步进 G3：在 `src/<lib>/rvv/` 写内核，
用 `-D_USE_RVV=ON` 交叉编译，真机跑 `pair_bench.sh` 拿加速比——那一步才有人拍板的收益问题。
