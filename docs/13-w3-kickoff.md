# W3 开工：10 项骨架、源码与首批 G2

W3 是 `data/waves.csv` 里的第三波（10 项 / 515 人日，依赖 W2）。本轮把这一波**全部立起来**：
10 个工程骨架、子模块、派工单就位；其中七项已推到 G2（native A/B + riscv64 交叉都一致）。
其余按依赖与语料条件卡在 G1，原因逐项写清，不做"占位式通过"。

## 1. 状态总表

| ID | 包 | 工程 | 难度 | 门禁 | 现状与卡点 |
|---|---|---|---|---|---|
| RVV-013 | media-libs/x264 | `x264-rvv` | D5 | **G2** | 10 帧 690 B 码流两侧一致（纯 C，`--disable-asm`） |
| RVV-014 | media-libs/zimg | `zimg-rvv` | D3 | **G2** | resize + depth 两条路径两侧哈希一致 |
| RVV-015 | media-libs/libde265 | `libde265-rvv` | D3 | **G2** | 用 x265 生成固定语料 `tiny-64x64.265`，解码 10 帧像素一致 |
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
x264     enc frames=10 bytes=690 fnv_bit=91e876b2b8b16d8c
libde265 dec frames=10 bytes=61440 fnv_px=cf67fb9981835c6a
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
6. **解码库的语料要自己造并固化**（libde265）：上游不带任何 HEVC 测试流；用 x265 在容器里
   编一个固定参数的小码流（4828 B），只把这个 `.265` 提交进仓库，x265 本身不进 A/B。
   顺带：`de265_get_image_plane_stride` 不存在，stride 从 `de265_get_image_plane(img,c,&stride)` 出参拿。
7. **上游没有 install 目标**（cryptopp）：`make static` 后只有 `libcryptopp.a` 和一堆散落头文件，
   前缀要自己造（头进 `prefix/include`、库进 `prefix/lib`），否则探针的
   `target_include_directories` 无处可指。

## 4. 下一步（按依赖排序）

W3 已 7/10 到 G2（x264、zimg、libde265、botan、crypto++、eigen、fftw）。剩下三项都是重的：

1. **gdal**：先定最小配置（只留 GTiff/VRT + 必要驱动），否则 configure 会拖进几十个可选依赖；
   源码体积大，拉取要单列一步。
2. **gromacs**：需要 FFT/MPI 依赖决策——基线可以先 `-DGMX_FFT_LIBRARY=fftw3 -DGMX_MPI=OFF`，
   用**已编好的 fftw-rvv 前缀**，正好复用 W3 里 fftw 的成果。
3. **ceph**：体量最大，先只取 `librados`/`libceph-common` 这类最小目标，别开全套 daemon。

## 5. 复现

```bash
cd ~/work/<pkg>-rvv
./scripts/native-baseline.sh   # 容器内 native A/B
./scripts/cross-baseline.sh    # 容器内 riscv64 + qemu-user
```
