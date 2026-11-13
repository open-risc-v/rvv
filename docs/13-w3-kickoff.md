# W3 开工：10 项骨架、源码与首批 G2

W3 是 `data/waves.csv` 里的第三波（10 项 / 515 人日，依赖 W2）。本轮把这一波**全部立起来**：
10 个工程骨架、子模块、派工单就位；其中五项已推到 G2（native A/B + riscv64 交叉都一致）。
其余按依赖与语料条件卡在 G1，原因逐项写清，不做"占位式通过"。

## 1. 状态总表

| ID | 包 | 工程 | 难度 | 门禁 | 现状与卡点 |
|---|---|---|---|---|---|
| RVV-013 | media-libs/x264 | `x264-rvv` | D5 | G1 | 骨架就位，源码未拉。`code.videolan.org` 已实测可匿名（`0480cb0`） |
| RVV-014 | media-libs/zimg | `zimg-rvv` | D3 | **G2** | resize + depth 两条路径两侧哈希一致 |
| RVV-015 | media-libs/libde265 | `libde265-rvv` | D3 | G1 | 源码就位；**缺 HEVC 码流语料**，上游不带测试流 |
| RVV-026 | dev-libs/botan | `botan-rvv` | D3 | **G2** | SHA-256 + CTR(AES-256) 两侧哈希一致（C++20） |
| RVV-027 | dev-libs/crypto++ | `cryptopp-rvv` | D3 | **G2** | SHA-256 + AES-256-CTR 两侧哈希一致 |
| RVV-028 | sys-cluster/ceph | `ceph-rvv` | D3 | G1 | 骨架就位；源码未拉（体量与依赖都大） |
| RVV-032 | dev-cpp/eigen | `eigen-rvv` | D4 | **G2** | 整数 matmul 逐位一致；双精度 matmul `max_rel≈2e-13`、量化哈希一致 |
| RVV-033 | sci-libs/fftw | `fftw-rvv` | D5 | **G2** | 1024 点复 FFT，`max_rel≈3e-14`、量化哈希一致；用 3.3.10 发布包 |
| RVV-034 | sci-libs/gdal | `gdal-rvv` | D3 | G1 | 骨架就位；需先定最小构建配置（否则拖进一堆驱动依赖） |
| RVV-035 | sci-chemistry/gromacs | `gromacs-rvv` | D5 | G1 | 骨架就位；源码与 MPI/FFT 依赖要专门准备 |

## 2. 五项 G2 的实测值（可直接当回归期望）

```
zimg     resize size=96x72 fnv=63a1b96d955d6536
         depth  size=64x48 fnv=1ca7dee4e96750f5
cryptopp sha256 fnv=ab0624b961d45259
         aesctr n=65536 fnv=6b642726bef75efc
botan    sha256 fnv=ab0624b961d45259
         aesctr n=65536 fnv=6b642726bef75efc
eigen    imatmul 64x64 fnv=b6934bd0094dc25a
         dmatmul 128x128 fnv=72dccc2fcdc7d3ba max_rel≈2e-13
fftw     dft1024 fnv=7c2af68f8fe41f90 max_rel≈3e-14
```

四项都是 native（容器内 aarch64）与 riscv64（qemu-user，`-march=rv64gc`）**逐字段相同**。
zimg 探针用 `ZIMG_CPU_NONE`、cryptopp 用纯 C++ 实现路径，所以基线阶段两侧没有 SIMD 分支差异。

## 3. 这一轮新暴露的三个骨架/上游坑（已写回 Skill）

1. **上游 submodule 不自动 init**（zimg 的 `graphengine`）：`make` 报
   `No rule to make target 'graphengine/graphengine/cpuinfo.cpp'`。`fetch-upstream.sh` 之后要
   `git -C baseline submodule update --init --recursive`，并把内容同步进 `src/`。
2. **C++ 库 + C 探针不能用 `-lstdc++`**：交叉 sysroot 只有 `libstdc++.so.6`，没有无版本号
   的 `.so`，链接直接失败。正确做法是 `set_target_properties(... LINKER_LANGUAGE CXX)`，
   并把 `project()` 写成 `C CXX`。
3. **浮点库要分两条判据**（eigen / fftw）：整数路径逐字节比，浮点路径先量化（1e-6）再取哈希，
   真实误差对 long double 参考单独打印、阈值 1e-12。只写"逐字节一致"会让末位舍入变成假红。
4. **FFTW 的 git 树编不出基线**：codelet（`n1_2.c`）由 OCaml `genfft` 生成，规则只在
   `--enable-maintainer-mode` 下存在；改用官方 3.3.10 发布包（含预生成 codelet，sha256 固定）。
   发布包还要 `make MAKEINFO=true` 躲开容器里没有 texinfo 的问题。
5. **Botan 3.x 是 C++20 且不认 `--host`**：探针要 `cxx_std_20`，交叉用
   `--cc-bin=riscv64-linux-gnu-g++ --os=linux --with-sysroot-dir=... --ar-command=...`。
6. **上游没有 install 目标**（cryptopp）：`make static` 后只有 `libcryptopp.a` 和一堆散落头文件，
   前缀要自己造（头进 `prefix/include`、库进 `prefix/lib`），否则探针的
   `target_include_directories` 无处可指。

## 4. 下一步（按依赖排序）

0. 轻量三项（eigen / fftw / botan）已完成 G2；下面按依赖继续。
1. **x264 拉源码**（已验证可匿名）→ configure `--host` → 探针（编码固定 YUV，比码流 + 解码像素）。
2. **libde265**：语料问题必须先解。最省事的路径是用 x264 同一波里的 HEVC 编码器生态，
   或直接取 libde265 上游 issue/测试仓里的最小 `.265` 文件（**需要能复现的固定文件，不接受随手截取**）。
3. **fftw**：先定容差口径（参考用同一份 double 纯 C DFT 在探针里算，输出相对误差 + 结构哈希）。
4. **botan / eigen**：接入方式已明确，属于纯工时。
5. **gdal / gromacs / ceph**：先写"最小构建配置"再拉源码，否则一次 clone + configure 会拖进几十个可选依赖。

## 5. 复现

```bash
cd ~/work/<pkg>-rvv
./scripts/native-baseline.sh   # 容器内 native A/B
./scripts/cross-baseline.sh    # 容器内 riscv64 + qemu-user
```
