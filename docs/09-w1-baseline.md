# W1 六项：第一个 A/B 版本全部跑通（G2）

> 2026-11-13。W1 的 6 个 P0 工程从"骨架 + 上游快照"推进到 **G2 baseline-green**：
> 每个工程都用上游自己的构建系统编出真实库，跑真实用例，A/B 逐字节一致。

## 1. 一眼看结果

| 工程 | 上游固定点 | 上游构建系统 | 真实用例（被测路径） | A 侧关键数字 |
|---|---|---|---|---|
| `pixman-rvv` | `3174212a` | meson | 129×97：fill `pixman_image_fill_boxes` + `composite32` OVER + 线性渐变 | `fnv=066ba2…`，`composite.ppm` 37553 B |
| `libjpeg-turbo-rvv` | `3ef3367e` | cmake | 128×96 RGB：q85/ISLOW 编码 → `jpeg_mem_src` 解码回环 | JPEG 2799 B，`fnv_px=79887a…` |
| `libpng-rvv` | `7ef5852d` | cmake | 131×99：全过滤类型 + zlib 6 编码 → 解码回环 | PNG 28936 B，`fnv_px=732284…` |
| `zlib-ng-rvv` | `6727d883` | cmake | 200003 B deflate(6) → inflate 回环 | 压缩后 73562 B，`crc=2644adc5` |
| `openssl-rvv` | `3f11738c` | perl Configure | 64 KiB：AES-128-CBC 关 padding 回环 + SHA-256 | `sha256=b5c66c…`，密文 `fnv=cc1849…` |
| `libgcrypt-rvv` | `88563e87` | autotools | 64 KiB：SHA-256 + AES-128-CBC 回环 | `sha256=8ae532…`，密文 `fnv=1b61c6…` |

六项 `./test/run_ab.sh` 均输出：

```
PASS 00_framework（2 个文件逐字节一致）
PASS 01_<pkg>_<功能>（2 个文件逐字节一致）
== A/B: ALL PASS（2 个用例，A=src vs B=baseline）==
```

## 2. 统一接法（一个工程三个文件）

| 文件 | 作用 |
|---|---|
| `cmake/pkg-build.sh` | 用上游自己的构建系统把 `$SRC_DIR` 编到 `<build>/pkg/prefix`（A/B 各一份前缀） |
| `cmake/upstream.cmake` | `add_custom_target(pkg ALL)` 调上脚本；探针 `add_dependencies(<pkg>_harness pkg)`，用 `target_link_directories` + `-l` 链接 |
| `test/pkg_<pkg>.c` + `test/cases/01_*.sh` | 确定性语料 → 真实 API 调用 → 落产物 + 哈希；用例断言产物大小/长度 |

A/B 的唯一变量仍是源码树：A 用 `src/`（上游快照 + 后续内核），B 用 `baseline/` 加
`RVV_KERNELS=OFF`。native 阶段两侧代码相同，所以"一致"是必然结果——这一步的价值是
**证明上游真能编进来、真实路径真能跑通**，不是证明加速。

## 3. 四种构建系统的实际代价

| 上游形态 | 代表 | 单侧构建 | 备注 |
|---|---|---|---|
| meson | pixman | 十几秒 | `-Ddefault_library=static` |
| cmake | libpng / zlib-ng / libjpeg-turbo | 十几秒 ~ 半分钟 | libjpeg-turbo 带 nasm，仍很快 |
| perl Configure | openssl | **分钟级，六项最慢** | out-of-source；两次 `make`（build_sw + install_sw），A/B 合计最贵 |
| autotools | libgcrypt | 半分钟 | 只有 `configure.ac`，要 `autoreconf`；为不弄脏 baseline，复制到 `<build>/pkg/src` 再生成 |

结论：**openssl 是 W1 的构建时间大头**，W2 里同类（perl Configure / 大 autotools）工程排期时
要把"每轮 A/B 都要重编上游"算进去；cmake/meson 类可以高频迭代。

## 4. 踩到的坑（已修，写进 Skill）

1. **静态库绝对路径当链接项** → 首次配置时库还没生成，CMake 报 `No rule to make target '*.a'`。
   改成 `target_link_directories` + `-l`，让链接发生在 `pkg` 目标之后。
2. **库名与系统库撞车**：libpng 装出来是 `libpng18.a`，链 `png16` 会静默连到系统 1.6.59，
   运行时报 `built with 1.8.0.git but running with 1.6.59`。**装完先 `ls prefix/lib` 核对真实库名。**
3. **语料太"好压"**：libpng 纯渐变 131×99 只压到 921 B，用例阈值失真。加确定性噪声
   （`x*1103515245 + y*12345`）后恢复到 28936 B，filter 分支才真正被覆盖。
4. **autotools 脏树**：libgcrypt 直接在 `baseline/` 跑 `autoreconf` 会改动唯一参照。
5. **源码树内 configure**：openssl 首版在 `src/` 里 `perl ./Configure`，把 `Makefile` 和 `.d` 写进了
   `baseline/`（该工程 `src`/`baseline` 差异 1890 行，全是生成物）。已改 out-of-source，
   重编后探针哈希不变（`sha256=b5c66c…`），两侧 `diff -r` 回到 0 行。
6. **快照漏文件**：openssl 自带 `.gitignore` 遮蔽了 26 个真实源码（含 `include/arch/riscv_arch.def`），
   `git add -A` 没纳入，`git clean -dfx` 把它们从 `src` 删掉了。已 `git add -f` 补全，
   现在三棵树的对照关系可复现。

## 5. 状态与证据

- `data/status.csv`：W1 六项 `G1 → G2`；看板 G0 42 / **G2 6** / 其余 0。
- 每工程 `docs/evidence/G2-20261113.md`（做法 + 命令 + 输出 + 局限）。
- 主仓库 `063b929`，六个子模块指针已 bump 到各自 G2 提交。
- `./scripts/verify.sh` → PASS。

## 6. 下一步（G3 的真实门槛）

1. `src/<lib>/rvv/` 落第一个 RVV 内核，`RVV_KERNELS=ON` 才产生代码差异；
2. `./scripts/build.sh riscv64` 第一次交叉编译（工具链就位与否待确认）；
3. 真机 `pair_bench.sh` 拿 A/B 比值 —— **G3 的判据是数字，不是 ALL PASS**；
4. openssl/libgcrypt 的 AES/SHA 是 RVV 加密扩展（ZVkn）与向量两条不同路线，先定路线再动内核。
