# 接入上游构建系统（G1 的核心工作）

骨架只构建工具（`cpu_probe`、`diff_kernels`），上游构建要在 `cmake/upstream.cmake` 里接。
目标只有一个：**A 与 B 两侧产出同名、可执行、行为可比的程序**。

## 1. 三条硬规则

1. A/B 的编译选项差异**只允许**一个：`RVV_KERNELS`（决定是否启用 `src/<lib>/rvv/` 的覆盖）。
   不要一侧 `-O2` 一侧 `-O3`，也不要一侧带 `-mtune=native`。
2. `baseline/` 只读。它的作用就是"可信参照"，任何补丁都会让 A/B 归零。
3. 源文件列表显式列出，不用 `file(GLOB)`；上游新增文件会悄悄改变基线。

## 2. CMake 上游（最省事）

```cmake
add_subdirectory("${SRC_DIR}/lib" "${CMAKE_BINARY_DIR}/upstream" EXCLUDE_FROM_ALL)
if(TARGET vpx)
  target_compile_options(vpx PRIVATE ${RVV_FLAGS})
  if(RVV_KERNELS)
    target_compile_definitions(vpx PRIVATE VPX_RVV_KERNELS)
  endif()
endif()
```

注意：`${RVV_FLAGS}`、`_USE_RVV`、`RVV_KERNELS` 已在顶层 CMakeLists 里定义好；
`SRC_DIR` 会由 `run_ab.sh` 切成 `src` 或 `baseline`，所以路径不要写死。

## 3. autotools / meson 上游（两条路，选一条）

**a) 委托构建（推荐，不改上游代码）**

由 `scripts/build.sh` 或 `scripts/device-test.sh` 先跑上游自己的构建，然后 A/B 用例通过
`$BIN/pkg/bin/<tool>` 调用。需要在骨架里加一个薄封装：

```
build/<preset>/pkg/     # 上游构建产物
```

`test/run_ab.sh` 里把 `$BIN` 传给用例，用例自己拼 `$BIN/pkg/bin/xxx` 即可，无需改框架。

**b) 抄源文件列表（换来编译选项可控）**

像 `libspeex-rvv` 那样，把上游参与构建的 `.c` 全部显式列出：

```cmake
set(SPEEX_SOURCES ${SPEEX_SRC_DIR}/libspeex/bits.c ...)
add_library(speex ${SPEEX_SOURCES})
```

好处：编译选项、宏、include 路径全在掌握；代价：上游加文件时要手动同步（写进 `docs/rvv-notes.md`）。

## 4. 用例怎么写（`test/cases/*.sh`）

契约：

| 环境变量 | 含义 |
|---|---|
| `STAGE` | `gen`（生成输入，只跑 A 侧）或 `run`（跑被测程序） |
| `SIDE` | `A` 或 `B` |
| `BIN` | 该侧构建目录（`build/ab-a` 或 `build/ab-b`） |
| `DATA` | 共享输入目录（两侧一致） |
| `OUT` | 本侧输出目录（框架会逐字节比较两个 OUT） |

要求：

- 产出必须是**确定性文件**：不要写时间戳、随机数、绝对路径、PID；
- 一个用例只测一类行为，便于失败定位；
- 没有产出文件会被判为 FAIL（防止"空跑通过"）；
- 生成输入用固定种子、固定长度，必要时把输入文件本身也放进 `OUT` 参与比较。

## 5. 上游是库（没有 CLI）时

不要为了测试去写一个大而全的 CLI。做法：在 `test/cases/` 里放一个小 C 程序
（编到 `$BIN/test/` 下），调库的公开 API，把输出写成文件。要点：

- 小程序的源文件放 `test/`，两侧用同一份，保证可比；
- 输入用固定常量数组，不用 `rand()`；
- 输出用 `fwrite` 二进制，不用 `printf`（浮点格式化会引入不确定性）。

## 6. 验证口径与用例的对应

| `VALIDATION` | 用例判据 | 额外要求 |
|---|---|---|
| bit-exact | `diff -r` 逐字节一致 | 交叉解码/往返也要比 |
| 一致 | 逐字节一致（同输入同输出） | 编码器还要给码率-质量漂移 |
| 容差 | 用例自己输出误差统计，框架只比结构 | 误差阈值写进 `docs/plan.md` |
| 集成+缺口 | 缺口清单 + 回退验证 | 无 RVV 目标必须能跑 |

容差类不要硬塞进字节比较：让用例输出一个 `metrics.txt`（含 max/P99 相对误差），
框架比结构，人看数值——并把阈值判定写进 `docs/perf-log.md`。

## 7. 已验证可用的接法（6 个真实包趟过，照这个抄）

一个工程三个文件，就能把上游真实库接进门禁：

**`cmake/pkg-build.sh`** —— 用**上游自己的**构建系统编到 `<build>/pkg/prefix`，
A/B 两侧各跑一次（`$1`=源码树，`$2`=输出目录）。四种上游按需选：

```bash
# meson（pixman）
meson setup "$OUT/bld" "$SRC" --prefix "$OUT/prefix" --libdir lib \
  --buildtype release -Ddefault_library=static >/dev/null
meson compile -C "$OUT/bld" >/dev/null && meson install -C "$OUT/bld" >/dev/null

# CMake（libpng / zlib-ng / libjpeg-turbo）
cmake -S "$SRC" -B "$OUT/bld" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$OUT/prefix" -DBUILD_SHARED_LIBS=OFF >/dev/null
cmake --build "$OUT/bld" -j >/dev/null && cmake --install "$OUT/bld" >/dev/null

# perl Configure（openssl）—— 必须 out-of-source：在 $OUT/bld 里 configure
mkdir -p "$OUT/bld" && cd "$OUT/bld"
perl "$SRC/Configure" --prefix="$OUT/prefix" --libdir=lib \
  no-shared no-tests no-docs --openssldir="$OUT/prefix/ssl" darwin64-arm64-cc >/dev/null
make -j8 build_sw >/dev/null && make install_sw >/dev/null

# autotools（libgcrypt：只有 configure.ac，先复制再 autoreconf，别弄脏 baseline）
cp -R "$SRC" "$OUT/src" && (cd "$OUT/src" && autoreconf -fi)
"$OUT/src/configure" --prefix="$OUT/prefix" --disable-shared --enable-static >/dev/null
make -j8 >/dev/null && make install >/dev/null
```

**`cmake/upstream.cmake`** —— 一个 `add_custom_target(pkg ALL COMMAND ...)`，加一个探针：

```cmake
add_custom_target(pkg ALL
  COMMAND "${CMAKE_CURRENT_SOURCE_DIR}/cmake/pkg-build.sh" "${SRC_DIR}" "${CMAKE_BINARY_DIR}/pkg"
  COMMENT "构建上游（${SRC_DIR}）" VERBATIM)
add_executable(<pkg>_harness test/pkg_<pkg>.c)
add_dependencies(<pkg>_harness pkg)
target_include_directories(<pkg>_harness PRIVATE "${CMAKE_BINARY_DIR}/pkg/prefix/include")
target_link_directories(<pkg>_harness PRIVATE "${CMAKE_BINARY_DIR}/pkg/prefix/lib")
target_link_libraries(<pkg>_harness PRIVATE <libname> m)
```

**`test/cases/01_<pkg>_<功能>.sh`** —— `run` 阶段跑 `$BIN/<pkg>_harness "$OUT/x.bin"`，
并断言产出大小/长度（防"空文件也算一致"）。

三条踩过的坑：

1. **不要把静态库写成绝对路径传给 `target_link_libraries`**：首次配置时库还不存在，
   CMake 会报 `No rule to make target '...a'`。用 `target_link_directories` + `-l` 形式。
2. **核对安装出来的库名**：libpng 出来的是 `libpng18.a` 而不是 `libpng16.a`，
   链接到系统库会看到 `built with 1.8.0 but running with 1.6.59` 的警告。
3. **perl Configure / autotools 这类默认在自己树里生成 Makefile 的上游**：一律 out-of-source
   （cmake 用 `-B`、meson 用独立 builddir、autotools 在 `$OUT/bld` 里跑 `$SRC/configure`）。
   一旦在源码树内 configure，`baseline/` 会被写进 `Makefile` 与 `.d`，"原始参照"就没了，
   而且下次构建会复用陈旧 `.o`。
4. **快照要 `git add -f`**：上游自带 `.gitignore` 会遮蔽部分真实源码（openssl 的
   `include/arch/riscv_arch.def`、`crypto/ia64cpuid.S` 等 26 个文件），普通 `git add -A`
   会漏掉它们，`git clean -dfx` 一跑就把文件删了。快照提交后核对 `diff -r src baseline` 必须为 0。
5. **语料要有噪声**：纯渐变/全零数据的压缩比高得离谱，会把 filter、deflate 分支掩盖掉，
   用例阈值也会失真。

## 7. 交叉编译基线（G3 的前置，已在 11 个包上验过）

> **编译一律在 Linux 容器里做，宿主（macOS）只当编辑器。**
> native 侧也一样：`./scripts/native-baseline.sh` 把 `run_ab.sh` 丢进同一个镜像跑，
> 这样 native 与 riscv 共享同一套 glibc/工具链，差异只来自架构。
> 好处很实在：webrtc-audio-processing 的 `examples` 在 macOS 上缺 CoreFoundation 链接，
> 换成 Linux 容器直接就好了，不用为宿主平台的怪问题打补丁。

native 上的 A/B 只证明"上游能编、真实路径能跑"。要碰 RVV 内核，先得证明**同一份上游在
riscv64 上也能编、能跑、输出与 native 一致**，否则后面任何失配都分不清是内核写错还是
交叉链路搭错。

### 7.1 容器与口径

| 项 | 值 |
|---|---|
| 镜像 | `rvv-cross:1`（Ubuntu 24.04 + `riscv64-linux-gnu-gcc 13.3` + `qemu-riscv64` + cmake/ninja/meson/autotools/pkg-config） |
| 目标 | `riscv64-linux-gnu`，sysroot `/usr/riscv64-linux-gnu` |
| 基线口径 | `-march=rv64gc`（**不带向量**）。向量留给内核阶段用 `rv64gcv` |
| 执行 | `qemu-riscv64 -L /usr/riscv64-linux-gnu <binary>`，**只判功能，不出性能** |
| 产物 | `build/riscv64-b/{bld,prefix,harness,out}` |

`./scripts/cross-baseline.sh` 一次做完：编上游 → 装前缀 → 编探针 → qemu 跑 → 打印
riscv 与 native 两行哈希。骨架已带这个脚本（CMake 上游直接可用，每种构建系统只改"编上游"一段）。

### 7.2 四类构建系统的交叉写法（实测）

- **CMake**：`cmake -S baseline -B <out>/bld -DCMAKE_TOOLCHAIN_FILE=/work/cmake/toolchain-riscv64-linux.cmake
  -DCMAKE_INSTALL_PREFIX=/work/<out>/prefix`，再 `--build` / `--install`。
- **meson**：写 `cmake/meson-cross-riscv64.ini`（`c`/`cpp` 指 `riscv64-linux-gnu-gcc`、
  `exe_wrapper = 'qemu-riscv64 -L /usr/riscv64-linux-gnu'`、`needs_exe_wrapper = true`），
  然后 `meson setup <out>/bld baseline --cross-file cmake/meson-cross-riscv64.ini -Dc_args=-march=rv64gc`。
  meson 不允许 `-Dc_args` 覆盖 cross 文件里已有的 `c_args`，把 march 写进 cross 文件更稳。
- **autotools**：`cp -R baseline <out>/src` 后 `autoreconf -fi`，再 `./configure --host=riscv64-linux-gnu
  --prefix=... --disable-shared --enable-static`。**不要在 baseline 里 autoreconf**（会脏）。
- **perl Configure（openssl）**：`CC=riscv64-linux-gnu-gcc perl baseline/Configure --prefix=...
  no-shared no-tests linux64-riscv64 -march=rv64gc`，`make build_sw` + `make install_sw`；
  汇编路径不通时退 `linux64-riscv64-noasm`。

### 7.3 十四条实测坑

1. **探针要能跳过 pkg 目标**：交叉时上游已由脚本编好，`cmake/upstream.cmake` 必须写成
   `if(NOT DEFINED PKG_PREFIX) ... endif()` + `if(HAVE_PKG_TARGET) add_dependencies(...)`，
   否则 configure 阶段又回头编一遍 native 上游。
2. **依赖库只有宿主架构那一份**：容器 `/usr/riscv64-linux-gnu/lib` 里有 zlib 但**没有**
   libgpg-error。上游依赖的第三方库要么自己交叉编（见下），要么用 `-D<NAME>_ROOT` 指到
   你编好的 riscv 前缀。
3. **`gpg-error.h` 不随交叉编的库走**：libgcrypt 的探针要 `-DGPGERR_ROOT=<prefix>`
   同时给 include 和 lib，不能靠 `pkg-config`（它返回宿主架构的路径）。
4. **压缩实现不同 ⇒ 字节不同**：libpng 若用 zlib-ng 当 zlib 提供方，riscv 与 native 的
   PNG 字节会不同（deflate 实现不同），但**解码像素哈希必须一致**。判据要写清是
   "码流一致"还是"像素一致"，别把两者混成一个 PASS。
5. **静态库链接用 `-l` 不用绝对路径 `.a`**：绝对路径在生成 Makefile 时会被当依赖目标，
   报 `No rule to make target`。
6. **`run_ab.sh` 必须用 `bash` 执行用例**：Ubuntu 的 `/bin/sh` 是 dash，用例开头的
   `set -euo pipefail` 会直接失败，于是**所有用例被算成 SKIP**，最后还打印
   "ALL PASS（0 个用例）"——这是最危险的假绿。骨架已改成 `run bash`，并把 SKIP 计为 FAIL。
7. **meson 的 `exe_wrapper` 要带 sysroot**：只写 `qemu-riscv64` 会报
   `Executables created by c compiler are not runnable`；要写
   `exe_wrapper = ['qemu-riscv64', '-L', '/usr/riscv64-linux-gnu']`（数组形式）。
8. **meson 静态库是 thin archive**：成员按相对路径引用，`cp` 到别的目录后
   `ar` 直接报 `No such file or directory`，而 `ar x` 也不支持 thin。
   要合并/转存只能**从 `*.a.p/*.o` 目标目录重新 `ar rcs`**；上游有多个静态库
   （如 APM 之外的 isac/rdft）时把所有 `*.a.p` 的 `.o` 都收进来，否则链接缺符号。
   多个归档合并成一个归档是安全的（单归档有符号索引，成员顺序无关）。
9. **上游 submodule 不会自动 init**：`fetch-upstream.sh` 只 clone 主仓，`graphengine` 这类
   子模块是空目录，`make` 会报 `No rule to make target 'graphengine/graphengine/cpuinfo.cpp'`。
   拉完源码要 `git -C baseline submodule update --init --recursive`，再把内容同步进 `src/`
   （版本由主仓的 gitlink 固定，天然可复现）。
10. **C++ 库 + C 探针不要写 `-lstdc++`**：交叉 sysroot 里通常只有 `libstdc++.so.6`，
   没有无版本号的 `.so` 符号链接，`-lstdc++` 直接 `cannot find`。用
   `set_target_properties(<t> PROPERTIES LINKER_LANGUAGE CXX)`（并把 `project()` 写成 `C CXX`），
   让 C++ 驱动去解析运行时。
11. **上游没有 install 目标时自己造前缀**（cryptopp 是 `make static`）：头进
   `prefix/include`、库进 `prefix/lib`，否则探针的 include/link 目录无处可指。header-only 的包
   （eigen）同样要造前缀——只是"安装"变成拷头。
12. **浮点包要两条判据**：整数路径逐字节比；浮点路径先量化（`round(x*1e6)/1e6`）再取哈希，
   同时对 `long double` 参考打印 `max_rel`、阈值 1e-12。否则末位舍入会让基线永远"假红"。
13. **git 树编不出基线的包改用官方发布包**：FFTW 的 codelet（`n1_2.c`）由 OCaml `genfft` 生成，
   规则只在 `--enable-maintainer-mode` 下存在；发布包自带预生成 codelet，用 sha256 固定即可。
   发布包常要 `make MAKEINFO=true`（容器无 texinfo），C 探针也别 `#include <complex.h>`
   （会把 `fftw_complex` 解析成 C99 复数，`out[k][0]` 直接编不过）。
14. **不是所有构建系统都认 `--host`**：botan 的 `configure.py` 要
   `--cc-bin=<triple>-g++ --os=linux --with-sysroot-dir=/usr/<triple> --ar-command=<triple>-ar`；
   另外 Botan 3.x 头文件是 C++20，探针要 `cxx_std_20`。

### 7.4 上游依赖一个新版本库时

容器里发行版带的版本可能太旧（Ubuntu 24.04 的 libgpg-error 是 1.47，而 libgcrypt 要求
≥1.56）。**不要改上游的版本检查**，也不要去猜下载地址；两条可行路：

- 用 `apt-get source <pkg>` 在容器里取**发行版源码包**（需要 `deb-src`），再
  `./configure --host=riscv64-linux-gnu --prefix=/opt/<pkg>` 交叉编；
- 直接把这份源码烤进镜像（`FROM rvv-cross:1` + `COPY` 源码 + 编译），让
  `scripts/cross-baseline.sh` 只挂载工程目录、不再联网。

版本仍不满足时，换更高版本发行版的源码（如 `debian:sid-slim`）在 **stage A 取源码**，
stage B 用原镜像的 riscv sysroot 编——跨发行版只借源码，不借 glibc。
