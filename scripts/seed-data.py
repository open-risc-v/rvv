#!/usr/bin/env python3
"""从输入表格与人工判断，生成 data/inventory.csv 与 data/plan.csv。

用法：
    python3 scripts/seed-data.py [xlsx 路径]

输入：simd_x86_aarch64+in+chromium.xlsx（两张 sheet，按 ISA 列出 Gentoo 包）
输出：data/inventory.csv（167 行全量）、data/plan.csv（48 行核心计划）

判断口径见 docs/01-difficulty-rubric.md、docs/02-priority-rules.md。
所有工作量为经验估算（人日），不是实测值。
"""
import csv
import os
import sys

try:
    import openpyxl
except ImportError:
    sys.exit("需要 openpyxl：python3 -m pip install openpyxl")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    ROOT, "simd_x86_aarch64+in+chromium.xlsx")

# ---------------------------------------------------------------- 核心项目（人工判断）
# (pkg, project, probe_key, license, rvv_upstream, path, D, pd_low, pd_high,
#  validation, priority, wave, deps, 难点, 立项理由)
CORE = [
 ("media-libs/libjpeg-turbo","libjpeg-turbo-rvv","libjpeg-turbo","IJG/BSD","Y","A","D3",8,12,"bit-exact","P0","W1","-",
  "上游已有 15 个 simd/riscv64/*-rvv.c（颜色转换、采样、DCT、量化）；缺口是 2x2 upsample、Huffman、12-bit 路径；风险在 DCT 定点精度与 JPEG 输出逐字节一致",
  "每次图像解码的必经之路；上游已铺好内核，ROI 最高"),
 ("x11-libs/pixman","pixman-rvv","pixman","MIT","partial","A+B","D4",20,30,"bit-exact","P0","W1","-",
  "上游 pixman-rvv.c 只覆盖少量 fast path；x86 侧 22 个 SIMD 文件，算子×格式×bpp 组合爆炸；饱和管线与 bilinear 采样最难对齐",
  "ChromiumOS/GTK 渲染底座，X11 路径的合成性能直接决定桌面流畅度"),
 ("media-libs/libpng","libpng-rvv","libpng","libpng-2.0","Y","A","D2",3,5,"bit-exact","P0","W1","zlib-ng",
  "filter 已有 riscv/filter_rvv_intrinsics.c；缺口是 16-bit 与 interlace 路径；需确认无 RVV 机器上的 dispatch 安全回退",
  "网页/系统图像解码高频路径，工作量极小，属于必摘的果子"),
 ("sys-libs/zlib-ng","zlib-ng-rvv","zlib-ng","Zlib","Y","A","D2",3,5,"bit-exact","P0","W1","-",
  "arch/riscv 已有 adler32/chunkset/compare256/slide_hash/crc32_zbc；真正缺口是 longest_match（deflate 主循环）与 inflate 表驱动路径（后者不可向量化）",
  "压缩是网络与包管理的公共底座，且上游 RVV 已过半"),
 ("dev-libs/openssl","openssl-rvv","openssl","Apache-2.0","Y","A","D4",15,25,"bit-exact+常数时间","P0","W1","-",
  "已有 32 个 RISC-V 汇编（zkned/zvbb/zvkg/ghash/chacha 等）；缺口 SHA-256/512 RVV 与部分 bignum；常数时间约束与 perlasm 风格生成器是主要阻力",
  "TLS/证书全链路；ChromiumOS 与所有网络服务都依赖"),
 ("dev-libs/libgcrypt","libgcrypt-rvv","libgcrypt","LGPL-2.1+","Y","A","D4",10,18,"bit-exact","P1","W1","-",
  "已有 26 个（chacha/poly1305/gcm/rijndael/sha1）；缺口 sha256/512 与 mpi 大数；zvkned 路径需要运行期 hwprobe 分派",
  "GnuPG/GnuTLS 依赖；与 openssl 共享大部分内核设计，可复用"),
 ("media-libs/opencv","opencv-rvv","opencv","Apache-2.0","partial","A+D","D5",60,120,"容差+部分 bit-exact","P0","W2","eigen",
  "679 个 SIMD 路径（395 x86 / 58 neon / 83 riscv）；上游有 hal/riscv-rvv 与 universal intrinsics 的 RVV 后端；缺口在 DNN/视频模块与 3rdparty（后者已自带 libpng/zlib-ng 的 RVV）；按模块分批推进",
  "ChromiumOS 图像/ML 预处理的核心依赖，也是通用发行版的高频依赖"),
 ("media-libs/libwebp","libwebp-rvv","libwebp","BSD-3","N","B","D3",20,30,"一致","P0","W2","libpng/zlib-ng",
  "36 个 SIMD 文件（24 x86 / 12 neon），无 RVV；内核是 YUV→RGB、alpha、lossless predictor；编码器可容差，解码器输出需一致",
  "Web 图像的主要格式之一，Chromium 解码路径"),
 ("media-libs/libvpx","libvpx-rvv","libvpx","BSD-3","N","C","D5",120,200,"bit-exact（解码）","P0","W2","-",
  "325 个 SIMD 路径，x86 .asm + NEON 汇编；首期只做 decoder 关键子集（idct/itxfm/mc/loopfilter）覆盖 60–70% 热点；汇编语义复原 + 位精确是最大成本",
  "WebRTC/Chromium 视频主路径；不做则整机视频功耗与帧率不达标"),
 ("media-libs/libaom","libaom-rvv","aom","BSD-2","unknown","C","D5",100,160,"bit-exact（解码）","P1","W2","libvpx 经验",
  "AV1 内核面比 VP9 更宽（CDEF、loop restoration、warped motion）；克隆失败，RVV 现状待核实；建议只做解码 + 关键内核",
  "AV1 是 Chromium 的下一代默认编解码，但可先由标量路径顶住"),
 ("media-libs/openh264","openh264-rvv","openh264","BSD-2","N","C","D4",60,90,"bit-exact","P0","W2","-",
  "83 个 SIMD 文件、x86 asm + 32 个 NEON 汇编；核心是 SAD/SATD/DCT/deblock/MC；先按 C 参考写 intrinsics 版，再决定是否落 .S",
  "WebRTC 实时编码，出货路径"), 
 ("media-libs/x264","x264-rvv","x264","GPL-2.0","N","C","D5",80,120,"一致（编码可容差）","P1","W2","-",
  "全汇编（x86 mmx/sse2/avx + neon）；先做 SAD/SATD/DCT/deblock 子集；编码器不要求逐字节一致，但 RD 决策变化会导致码率/质量漂移，需码率-质量对照",
  "ffmpeg/录屏/转码的默认编码器，通用发行版高频"),
 ("media-libs/x265","x265-rvv","x265","GPL-2.0","unknown","C","D5",100,150,"一致","P2","W2","libde265",
  "HEVC 编码，AVX2 内核极多；克隆失败待核实；建议在 x264 完成后复用方法论，避免并行踩同一类汇编语义坑",
  "4K/HEVC 转码场景需要，非出货路径"),
 ("media-libs/zimg","zimg-rvv","zimg","WTFPL","N","B","D3",20,30,"容差","P1","W2","-",
  "40 个 SIMD 文件（28 x86 / 12 neon）；resize/colorspace/bitdepth 三类内核；浮点容差可接受，但缩放滤波器系数必须与 C 版一致",
  "ffmpeg/vapoursynth 的缩放与色彩转换后端，间接影响所有视频路径"),
 ("media-libs/libde265","libde265-rvv","libde265","LGPL-3","N","B","D3",25,35,"bit-exact（解码）","P1","W2","-",
  "17 个 SIMD 文件、15 个 x86 SSE4；mc/idct/deblock/SAO；HEVC 解码器 bit-exact 是硬门",
  "ChromiumOS HEVC 解码路径；与 x265 构成 HEVC 一对"),
 ("media-video/ffmpeg","ffmpeg-rvv","ffmpeg","LGPL-2.1/GPL-2.0","Y","A+C","D4",40,80,"bit-exact（fate）","P0","W2","libvpx/libaom/openh264/zimg/libde265",
  "已有 151 个 RISC-V 文件（libavcodec/riscv/*.S 为主）；缺口是 swscale、hevc、部分 dsp；必须用上游 checkasm/fate 做位精确回归，自建 A/B 不足以覆盖",
  "媒体栈的总入口；它把上面所有 codec 的收益放大到整机"),
 ("media-libs/opus","opus-rvv","opus","BSD-3","N","B","D3",15,25,"bit-exact（解码）","P0","W3","-",
  "45 个 SIMD 文件（26 x86 / 12 neon）；CELT 的 MDCT/pitch/comb filter 是主体；解码位精确、编码可容差；定点/浮点两条路径需分别处理",
  "WebRTC 音频主 codec，实时通信不可绕开"),
 ("media-libs/speexdsp","speexdsp-rvv","speexdsp","BSD-3","N","B","D2",8,12,"bit-exact","P1","W3","speex",
  "与 libspeex 共享定点滤波器结构，可直接迁移 libspeex-rvv 的 filters_rvv/QMF 经验；主体是重采样与回声消除",
  "回声消除/重采样在语音链路里，且已有同构成果可复用"),
 ("media-libs/speex","libspeex-rvv（已立项）","speex","BSD-3","N","B","D2",0,2,"bit-exact","P3","W3","-",
  "已完成样本：21 个 RVV 覆盖点、X60 真机编码 -63.8%；本行仅登记引用，不重复立项",
  "作为模板与校准锚点，不再消耗产能"),
 ("media-libs/webrtc-audio-processing","webrtc-ap-rvv","webrtc-ap","BSD-3","N","B","D3",30,45,"确定性","P0","W3","opus",
  "32 个 SIMD 文件（16 x86 / 9 neon）；AEC3 的 FFT 与分块相关、NS 的维纳滤波；10ms 帧实时约束，须做时延尾部测试，优化不得改变对齐行为",
  "ChromiumOS 实时通信的音频前端，延迟敏感"),
 ("media-libs/flac","flac-rvv","flac","BSD-3","N","B","D2",6,10,"bit-exact","P1","W3","-",
  "16 个 SIMD 文件；主体是 LPC 与 stereo decorrelation；无损格式必须位精确",
  "无损音频与音乐库场景，工作量小"),
 ("media-libs/openal","openal-soft-rvv","openal-soft","LGPL-2.0","N","B","D2",6,10,"容差","P2","W3","-",
  "8 个 SIMD 文件；混音与重采样；音频混合可容差，但需频谱一致性抽检",
  "游戏与桌面音频输出；非出货关键路径"),
 ("media-sound/mpg123","mpg123-rvv","mpg123","LGPL-2.1","unknown","B","D2",8,12,"一致","P2","W3","-",
  "克隆失败，现状待核实；主体是 Layer III 合成滤波器与 DCT36；解码输出应与参考实现一致",
  "MP3 解码在旧媒体链路里仍有需求"),
 ("media-sound/pulseaudio","pulseaudio-rvv","pulseaudio","LGPL-2.1","N","B","D2",5,8,"容差","P2","W3","-",
  "8 个 SIMD 文件，集中在重采样；收益小",
  "桌面音频路由；优先级低"),
 ("dev-libs/nettle","nettle-rvv","nettle","LGPL-2.1/GPL-2.0","N","C","D4",20,30,"bit-exact","P1","W4","-",
  "9 个 SIMD 文件（6 个 arm 汇编），大量内核写在 arm asm 里；主体是 memxor/sha/aes 与 mpn 大数；需与 zbkb/zkn 扩展组合",
  "GnuTLS 密码底座，与 openssl/libgcrypt 共享算法但实现独立"),
 ("dev-libs/botan","botan-rvv","botan","BSD-2","partial","B","D3",25,40,"bit-exact+常数时间","P1","W4","-",
  "134 个 SIMD 文件，但 RISC-V 只有 cpuid 探测；需新增 riscv64 SIMD 模块；Botan 有自建 SIMD 抽象层，接口清晰",
  "C++ 生态里最常用的密码库，抽象层友好"),
 ("dev-libs/crypto++","cryptopp-rvv","cryptopp","Boost-1.0","N","B","D3",30,50,"bit-exact","P1","W4","-",
  "123 个 SIMD 文件、大量小内核与模板特化；可用 SIMDe 快速起步（接口洁癖少），再对热点手写",
  "存量 C++ 项目依赖广，适合用 SIMDe 换时间"),
 ("net-libs/mbedtls","mbedtls-rvv","mbedtls","Apache-2.0","N","B","D2",10,15,"bit-exact","P2","W4","-",
  "仅 3 个 SIMD 文件，主体是大数 C 实现；收益有限，重点是 bignum 的 64 位乘加与朴素蒙哥马利",
  "嵌入式 TLS 常用；整机收益小"),
 ("dev-libs/rocksdb","rocksdb-rvv","rocksdb","Apache-2.0/GPL-2.0","N","B","D2",5,8,"bit-exact","P2","W4","-",
  "12 个 SIMD 文件，主要是 crc32c 与 memcpy；接 zbc 的 crc32 即可，收益集中在压缩/校验",
  "存储引擎，收益集中在校验和与块拷贝"),
 ("sys-cluster/ceph","ceph-rvv","ceph","LGPL-2.1","partial","B","D3",20,35,"bit-exact","P1","W4","rocksdb",
  "crc32c_zbc 已有；缺口是 ISA-L 风格的纠删码（GF 运算）与压缩；需重建 jerasure 的 GF 乘法表",
  "分布式存储底座；纠删码是 CPU 密集路径"),
 ("dev-libs/hyperscan","hyperscan-rvv","hyperscan","BSD-3","N","D","D5",80,150,"逐匹配一致","P2","W4","-",
  "22 个 SIMD 文件全是 SSSE3/AVX2 的 pshufb/比较骨架；RVV 没有 pshufb 等价（vrgather 成本高），需重设计 Teddy/Shufti；建议先做 autovec 后端 + 关键匹配器",
  "IDS/内容过滤的核心引擎，架构级改造风险高"),
 ("dev-cpp/eigen","eigen-rvv","eigen","MPL-2.0","Y","A+D","D4",15,25,"容差","P1","W5","-",
  "已有 arch/RVV10 全后端；缺口在 GEMM blocking/packing、Complex 与 FP16 覆盖、VLEN 无关性与 gcc 版本兼容；主要工作是调优而非从零",
  "TensorFlow/OpenCV/PCL 的公共数学底座，杠杆最高"),
 ("sci-libs/fftw","fftw-rvv","fftw3","GPL-2.0","N","D","D5",50,80,"容差","P1","W5","-",
  "108 个 SIMD 文件、0 个 RISC-V；codelet 生成器 + simd-vectors 抽象层是主体；必须新增 SIMD 支持层而不是手写少数内核",
  "科学计算与音频/DSP 的 FFT 底座"),
 ("sci-libs/gdal","gdal-rvv","gdal","MIT/X11","N","B","D3",20,35,"容差","P1","W5","-",
  "101 个 x86 SIMD 路径，集中在重采样/warp；栅格数据量大利于向量化；SIMD 多在内联函数而非独立文件",
  "GIS 数据处理主力，数据并行度高"),
 ("sci-chemistry/gromacs","gromacs-rvv","gromacs","LGPL-2.1","N","D","D5",60,100,"容差","P1","W5","eigen",
  "482 个 SIMD 命中，核心是 NBNXM 非键合与 PME；gromacs 自带 simd/simd4 抽象层，加 RVV backend 是正确入口；性能目标按同频 AVX2 比例定",
  "分子动力学标杆，HPC 客户的核心负载"),
 ("sci-libs/tensorflow","tensorflow-rvv","tensorflow","Apache-2.0","N","D","D5",100,200,"容差","P2","W5","eigen",
  "671 个 SIMD 命中，真正入口是 XNNPACK/RUY + Eigen；优先 TFLite（ChromiumOS ML 路径）；上游无 RISC-V 内核，需移植 xnnpack 的 rvv kernels",
  "端侧推理的主路径，但可先用 Eigen RVV 顶住"),
 ("media-libs/embree","embree-rvv","embree","Apache-2.0","N","D","D5",60,100,"容差","P2","W5","-",
  "45 个 SIMD 文件、SSE/AVX 4/8-wide 语义；BVH 遍历与构建需按可变 VLEN 重排；仅在渲染场景有价值",
  "光线追踪内核，收益场景窄但技术代表性高"),
 ("sci-libs/pcl","pcl-rvv","pcl","BSD-3","N","B","D3",15,25,"容差","P2","W5","eigen",
  "18 个 SIMD 命中；主体是点云滤波/法线估计/KD-tree；收益中等",
  "机器人/3D 感知常用，依赖 Eigen"),
 ("sci-libs/dlib","dlib-rvv","dlib","Boost-1.0","N","B","D3",20,30,"容差","P2","W5","-",
  "54 个 SIMD 文件（14 x86 / 6 neon）；DNN 与图像处理内核；矩阵乘依赖 BLAS 时可以借力 Eigen RVV",
  "人脸/视觉传统算法库，场景明确"),
 ("www-client/chromium","chromium-rvv","chromium","BSD-3","partial","A+D","D5",150,300,"集成+缺口","P0","W6","全部 W1–W5",
  "3410 个 x86 SIMD 路径大多在 third_party（libpng/zlib/icu 的重复）；真工作量在 Skia SkOpts、V8 wasm SIMD、ANGLE；定位是集成 + 缺口，不做全量重写",
  "整机体验的最终承载者，但必须等底层库完成后再做"),
 ("net-libs/nodejs","node-rvv","node","MIT","partial","D","D5",60,120,"集成","P2","W6","-",
  "2615 个 SIMD 路径主要是 V8/third_party；实际依赖 LLVM/GCC 代码生成与 V8 内置；不作为内核移植项目",
  "服务端 JS 运行时，收益间接"),
 ("dev-lang/rust","rust-rvv","rust","MIT/Apache-2.0","toolchain","D","D5",0,5,"-","P3","W6","-",
  "本身不做 SIMD 移植；RVV 能力取决于 LLVM 后端质量，归入 W0 工具链跟踪",
  "不立项，仅跟踪 LLVM RVV 代码生成质量"),
 ("dev-lang/go","go-rvv","go","BSD-3","partial","C","D3",40,70,"一致","P3","W6","-",
  "自带汇编器与 runtime；有 riscv64 支持但无 RVV 内核；需按 Go asm 语法新增，收益在 crypto/math/big 与 runtime memmove",
  "服务端运行时，收益集中在少数包"),
 ("media-video/vlc","vlc-rvv","vlc","GPL-2.0","partial","A","D2",8,15,"一致","P3","W6","-",
  "已有 modules/isa/riscv（deinterlace/mixer/transform 的 RVV 汇编）；缺口是 yadif 等 filter；验证 + 扩展即可",
  "桌面播放器，收益有限但成本极低"),
 ("media-tv/kodi","kodi-rvv","kodi","GPL-2.0","N","B","D3",20,35,"容差","P2","W6","ffmpeg",
  "92 个 SIMD 路径（89 x86）；主体是图像缩放/色彩转换/YADIF；多数可借 ffmpeg swscale 的成果",
  "媒体中心场景，可复用 ffmpeg 成果"),
 ("media-libs/libsdl2","SDL2-rvv","SDL","Zlib","N","B","D3",15,25,"一致","P3","W6","-",
  "23 个 x86 SIMD 文件；blit/缩放/YUV；需保证与参考 blit 逐像素一致",
  "游戏与模拟器的显示底座"),
 ("games-board/stockfish","stockfish-rvv","Stockfish","GPL-3.0","partial","B","D3",20,35,"一致（走子/评估）","P3","W6","-",
  "NNUE int8 点积是主体，RVV 收益大；但走子生成与评估必须逐位一致，回归成本高于内核成本",
  "棋类引擎，象征意义大于整机收益"),
 ("app-crypt/johntheripper","john-rvv","john","GPL-2.0","N","B","D3",30,50,"bit-exact","P3","W6","-",
  "26 个 SIMD 文件、按哈希格式分散；收益集中在少数格式；用途窄",
  "口令审计工具，场景窄"),
]

# ------------------------------------------------------- 长尾（粗档判断）
# pkg -> (D, band, priority, note)
LONG = {
 "app-benchmarks/ramspeed":("D1","S","P3","基准工具本身即测速程序，无移植价值"),
 "app-crypt/veracrypt":("D2","M","P3","SSE2 在加密卷 AES/XTS；收益限于磁盘加密场景"),
 "app-i18n/uchardet":("D1","S","P3","字符集探测，几乎无 SIMD"),
 "chromeos-base/aosp-frameworks-ml-nn":("D3","M","P2","NNAPI 后端，无自有内核，能力取决于 TFLite/XNNPACK 的 RVV 程度"),
 "chromeos-base/chrome-icu":("D2","S","P2","ICU 的 SIMD 面很小（collation/正则），收益低"),
 "chromeos-base/chromeos-chrome":("D5","XL","P0","与 www-client/chromium 同一代码库，并入 chromium-rvv，不独立立项"),
 "chromeos-base/common-assets":("D1","S","P3","资产打包，无 SIMD"),
 "dev-db/mongodb":("D4","L","P3","WiredTiger/压缩/哈希；SIMD 主要在 crc32c 与 JSON；整机不跑"),
 "dev-games/clanlib":("D2","S","P3","2D 游戏库，SSE2 在 blit"),
 "dev-games/simgear":("D2","M","P3","飞行模拟器基础库，矩阵/几何运算"),
 "dev-haskell/hashable":("D1","S","P3","GHC primops，无 intrinsic；由 GHC RISC-V 后端决定"),
 "dev-haskell/th-abstraction":("D1","S","P3","同上，纯类型层"),
 "dev-haskell/integer-logarithms":("D1","S","P3","同上"),
 "dev-haskell/cryptonite":("D3","M","P3","Haskell 密码库，内联汇编/prim；依赖 GHC 的 RISC-V 支持"),
 "dev-java/openjfx":("D2","M","P3","JavaFX 的 SSE2 渲染辅助；收益低"),
 "dev-lang/spidermonkey":("D4","L","P3","JS 引擎，与 V8 同类；工作量巨大且非出货路径"),
 "dev-lang/rust-bin":("D1","S","P3","预编译包，同 rust"),
 "dev-libs/gf2x":("D3","M","P3","GF(2) 多项式乘法，SSE2/SSE3 内核；数学库小众"),
 "dev-libs/xapian":("D3","M","P3","搜索引擎，SSE/SSE2 在排序与打分"),
 "dev-libs/efl":("D2","M","P3","Enlightenment 基础库，NEON 在图像/内存拷贝"),
 "dev-libs/ntl":("D3","L","P3","数论库，AVX2 在模运算；小众"),
 "dev-libs/openssl-compat":("D1","S","P3","兼容包，价值同 openssl"),
 "dev-libs/xerces-c":("D2","S","P3","XML 解析，SSE2 极少"),
 "dev-lisp/ecls":("D1","S","P3","Lisp 运行时，无自有 SIMD"),
 "dev-python/pypy-exe":("D3","M","P3","JIT 后端，SSE2 在内联汇编；依赖后端代码生成"),
 "dev-python/pypy3-exe":("D3","M","P3","同上"),
 "dev-util/biew":("D1","S","P3","二进制查看器，无移植价值"),
 "games-board/gnubg":("D3","M","P3","双陆棋引擎，NNUE 风格评估 + AVX；同类 stockfish"),
 "games-emulation/mupen64plus-core":("D3","L","P3","N64 模拟器，SSE 在 RSP/音频；复古场景"),
 "games-emulation/mupen64plus-video-glide64mk2":("D2","M","P3","图形插件，SSE 纹理路径"),
 "games-emulation/mupen64plus-video-rice":("D2","M","P3","同上"),
 "games-simulation/openttd":("D2","S","P3","运输模拟，SSE 极少"),
 "games-simulation/flightgear":("D2","M","P3","飞行模拟，矩阵/地形运算"),
 "games-strategy/megaglest":("D2","M","P3","RTS 引擎，SSE/SSE2"),
 "games-strategy/ufoai":("D2","M","P3","同上"),
 "gui-apps/waypipe":("D2","M","P2","AVX2 在像素转换/视频封装；远程桌面场景"),
 "mail-client/thunderbird":("D4","L","P3","与 firefox 同源，巨大且非出货路径"),
 "media-gfx/darktable":("D3","L","P3","RAW 处理，SSE3 在去马赛克/降噪；收益可观但非出货"),
 "media-gfx/openvdb":("D3","L","P3","稀疏体积，AVX；渲染管线专用"),
 "media-gfx/gimp":("D2","M","P3","图像编辑器，SSE 辅助"),
 "media-gfx/enblend":("D2","M","P3","图像融合，SSE2"),
 "media-gfx/libimagequant":("D2","S","P3","调色板量化，SSE2；小"),
 "media-gfx/luminance-hdr":("D2","M","P3","HDR 合成，SSE2"),
 "media-gfx/nvidia-texture-tools":("D2","S","P3","纹理压缩，SSE2"),
 "media-gfx/pngquant":("D1","S","P3","量化工具，本身小"),
 "media-libs/webrtc-apm":("D3","M","P0","即 webrtc-audio-processing 的旧原子名，并入 webrtc-ap-rvv"),
 "media-libs/devil":("D2","S","P3","图像库，SSE/SSE2 在格式转换"),
 "media-libs/glm":("D3","M","P2","header-only；SSE/AVX 特化矩阵；RVV 需新增路径，影响大量图形包"),
 "media-libs/graphene":("D2","S","P3","矩阵/四边形工具，NEON/SSE2"),
 "media-libs/babl":("D2","M","P3","色彩转换，AVX2；GIMP 依赖"),
 "media-libs/openimageio":("D3","L","P2","内置 simd.h 抽象；纹理/图像 IO；可复用其 SIMD 层"),
 "media-libs/osl":("D3","M","P3","着色语言，AVX；渲染专用"),
 "media-libs/spandsp":("D2","M","P3","传真/语音 DSP，SSE2"),
 "media-libs/openexr":("D3","M","P2","DWA/DCT + zip；影视管线常用，Chromium 不依赖"),
 "media-libs/libfreeaptx":("D2","S","P3","蓝牙 aptX 编解码，AVX2"),
 "media-libs/libpng-compat":("D1","S","P3","兼容包，价值同 libpng"),
 "media-libs/libopenaptx":("D2","S","P3","同上"),
 "media-libs/dumb":("D1","S","P3","音频解码小库，SSE 极少"),
 "media-libs/gd":("D1","S","P3","图形库，SSE 极少"),
 "media-libs/lensfun":("D2","M","P3","镜头畸变校正，SSE/SSE2"),
 "media-libs/vo-aacenc":("D3","M","P3","AAC 编码，NEON"),
 "media-libs/libsbsms":("D2","S","P3","音频变速，SSE"),
 "media-libs/libsoundtouch":("D2","M","P3","音频变速变调，SSE"),
 "media-libs/mlt":("D2","M","P3","媒体框架，SSE 在帧转换"),
 "media-libs/imlib2":("D2","S","P3","图像库，SSE2 在 blit"),
 "media-libs/libdvbcsa":("D2","M","P3","bitsliced DES，RVV 友好但用途窄"),
 "media-libs/libmikmod":("D1","S","P3","音乐模块播放，SSE2 极少"),
 "media-libs/netpbm":("D2","S","P3","图像工具集，SSE2"),
 "media-libs/opencolorio":("D2","M","P3","色彩管理，SSE2"),
 "media-libs/vidstab":("D2","M","P3","视频防抖，SSE2"),
 "media-libs/zita-resampler":("D2","S","P3","重采样，SSE2"),
 "media-plugins/calf":("D2","M","P3","音频插件，SSE"),
 "media-plugins/swh-plugins":("D1","S","P3","音频插件集，SSE 极少"),
 "media-plugins/vdr-dvbapi":("D1","S","P3","电视插件，SSE 极少"),
 "media-radio/fldigi":("D2","M","P3","数字通信调制解调，SSE/SSE2/SSE3"),
 "media-sound/ardour":("D2","M","P3","音频工作站，SSE 在混音"),
 "media-sound/jack-audio-connection-kit":("D2","S","P3","音频连接，SSE"),
 "media-sound/qtractor":("D1","S","P3","音频编辑器，GUI 为主"),
 "media-sound/supercollider":("D2","M","P3","音频合成，SSE/SSE2"),
 "media-video/ffmpeg-chromium":("D4","L","P0","ffmpeg 的 Chromium 补丁集，并入 ffmpeg-rvv"),
 "media-video/mplayer":("D2","M","P3","老播放器，SSE/SSE2"),
 "media-video/projectx":("D1","S","P3","TS 分析工具，SSE 极少"),
 "media-video/transcode":("D2","M","P3","转码工具集，SSE/SSE2"),
 "media-video/gpac":("D2","M","P3","MP4Box/播放，SSE2"),
 "net-analyzer/netdata":("D1","S","P3","监控代理，SSE2 极少"),
 "net-misc/freerdp":("D3","M","P3","RDP 解码，NEON/SSE 在 bitmap/RemoteFX"),
 "net-misc/zerotier":("D1","S","P3","组网，NEON 极少"),
 "net-p2p/cpuminer-opt":("D3","L","P3","SHA256d 挖矿，SSE2；收益高但用途窄"),
 "net-p2p/litecoind":("D3","M","P3","莱特币节点，scrypt"),
 "net-voip/yate":("D2","M","P3","语音交换，SSE2"),
 "net-vpn/i2pd":("D1","S","P3","I2P 节点，AVX 极少"),
 "net-wireless/yatebts":("D2","M","P3","基站协议栈，SSE3"),
 "sci-biology/fasttree":("D2","S","P3","系统发育，SSE3"),
 "sci-biology/raxml":("D3","M","P3","系统发育，SSE3"),
 "sci-biology/hmmer":("D3","M","P3","序列比对，SSE"),
 "sci-biology/bowtie":("D3","M","P3","短序列比对，SSE2"),
 "sci-biology/fasta":("D2","M","P3","序列比对，SSE2"),
 "sci-electronics/gazebo":("D2","M","P3","机器人仿真，SSE2"),
 "sci-libs/tensorflow-1.14.0":("D5","XL","P3","1.14 老版本，无 XNNPACK；不建议投入，用现代 TF 替代"),
 "sci-libs/visp":("D3","L","P3","视觉库，SSE2/SSE3；与 opencv 高度重叠"),
 "sci-libs/fflas-ffpack":("D3","L","P3","有限域线性代数，AVX/AVX2"),
 "sci-libs/dealii":("D4","L","P3","有限元，AVX；科学计算长尾"),
 "sci-libs/givaro":("D3","M","P3","有限域算术，AVX/AVX2"),
 "sci-libs/linbox":("D3","L","P3","精确线性代数，SSE/AVX"),
 "sci-libs/fcl":("D2","S","P3","碰撞检测，SSE"),
 "sci-libs/kissfft":("D1","S","P3","小 FFT，SSE；可用 RVV 快速覆盖"),
 "sci-libs/libcmatrix":("D2","S","P3","矩阵小库，SSE"),
 "sci-libs/cfitsio":("D2","S","P3","FITS 读写，SSE2"),
 "sci-libs/lis":("D2","M","P3","迭代求解器，SSE2"),
 "sci-libs/m4ri":("D3","M","P3","GF(2) 矩阵，SSE2"),
 "sci-mathematics/gret":("D2","S","P3","数论工具，AVX"),
 "sci-mathematics/gmp-ecm":("D3","M","P3","ECM 因子分解，SSE2；数论"),
 "sci-mathematics/gretl":("D2","M","P3","计量经济学，SSE2"),
 "sys-fs/dd-rescue":("D1","S","P3","数据救援，AVX2 极少"),
 "www-client/firefox":("D4","XL","P3","与 chromium 同类但非 ChromiumOS 出货路径"),
 "www-client/seamonkey":("D4","L","P3","Mozilla 套件，同源"),
 "www-plugins/lightspark":("D2","M","P3","Flash 模拟器，SSE2"),
 "x11-misc/fraqtive":("D1","S","P3","分形生成器，SSE2"),
}

# 已合并到其他项目的原子（不独立在册）
MERGED = {
 "chromeos-base/chromeos-chrome": "chromium",
 "media-video/ffmpeg-chromium": "ffmpeg",
 "media-libs/webrtc-apm": "webrtc-audio-processing",
}

PRIO_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
BAND_ORDER = {"S": 0, "M": 1, "L": 2, "XL": 3}


def read_sheet(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    inv = {}
    for ws in wb.worksheets:
        header = [str(c).strip() for c in next(ws.iter_rows(values_only=True)) if c]
        for row in ws.iter_rows(min_row=2, values_only=True):
            for i, v in enumerate(row):
                if not v:
                    continue
                atom = str(v).strip().rstrip("/-")
                rec = inv.setdefault(atom, {"isa": set(), "sheets": set()})
                rec["isa"].add(header[i].upper())
                rec["sheets"].add(ws.title)
    return inv


def short(atom):
    return atom.split("/")[-1]


def main():
    inv = read_sheet(XLSX)
    core = {row[0]: row for row in CORE}
    long = LONG

    # 补：核心表里有、但原表没有的原子（理论上不应发生）
    missing = [a for a in core if a not in inv]
    if missing:
        print("警告：核心项目不在输入表中：", missing)

    rows = []
    for atom, rec in inv.items():
        sh = short(atom)
        c = core.get(atom)
        if c:
            (pkg, project, probe, lic, rvv, pth, D, lo, hi,
             val, prio, wave, deps, note, why) = c
            isa = ",".join(sorted(rec["isa"]))
            proj = project
        else:
            d = long.get(atom)
            if d:
                D, band, prio, note = d
            else:
                D, band, prio = "D2", "M", "P3"
                note = "长尾：未单独评估，按 SIMD 面无参照的默认档处理，插单时重估"
            lo = hi = ""
            isa = ",".join(sorted(rec["isa"]))
            proj = ""
            val = ""
            wave = "-"
            deps = ""
        rows.append({
            "pkg": atom,
            "short": sh,
            "category": atom.split("/")[0],
            "source_sheets": "/".join(sorted(rec["sheets"])),
            "isa_paths": isa,
            "project": proj,
            "difficulty": D,
            "pd_low": lo,
            "pd_high": hi,
            "priority": prio,
            "wave": wave,
            "in_plan": "yes" if c else "no",
            "merged_into": MERGED.get(atom, ""),
            "note": note,
        })

    rows.sort(key=lambda r: (PRIO_ORDER.get(r["priority"], 9), r["category"], r["pkg"]))

    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    path = os.path.join(ROOT, "data", "inventory.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"inventory: {len(rows)} 行 -> {path}")

    # plan.csv
    plan = []
    for idx, row in enumerate(CORE, 1):
        (pkg, project, probe, lic, rvv, pth, D, lo, hi,
         val, prio, wave, deps, note, why) = row
        rec = inv.get(pkg, {"isa": set()})
        plan.append({
            "id": f"RVV-{idx:03d}",
            "pkg": pkg,
            "project": project,
            "upstream": probe,
            "license": lic,
            "isa_paths": ",".join(sorted(rec["isa"])),
            "rvv_upstream": rvv,
            "path": pth,
            "difficulty": D,
            "pd_low": lo,
            "pd_high": hi,
            "pd_plan": round((lo + hi) / 2 * 1.15),
            "validation": val,
            "priority": prio,
            "wave": wave,
            "deps": deps,
            "difficulty_notes": note,
            "rationale": why,
        })
    plan.sort(key=lambda r: (r["wave"], PRIO_ORDER.get(r["priority"], 9), r["id"]))
    for i, row in enumerate(plan, 1):
        row["id"] = f"RVV-{i:03d}"
    path = os.path.join(ROOT, "data", "plan.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(plan[0].keys()))
        w.writeheader()
        w.writerows(plan)
    print(f"plan: {len(plan)} 行 -> {path}")

    totals = {}
    for r in plan:
        t = totals.setdefault(r["wave"], [0, 0, 0])
        t[0] += r["pd_low"]
        t[1] += r["pd_high"]
        t[2] += r["pd_plan"]
    print("\n波次汇总（人日）：")
    for w_ in sorted(totals):
        lo, hi, p = totals[w_]
        print(f"  {w_}: 低 {lo} / 高 {hi} / 计划 {p}")
    lo = sum(t[0] for t in totals.values())
    hi = sum(t[1] for t in totals.values())
    p = sum(t[2] for t in totals.values())
    print(f"  合计: 低 {lo} / 高 {hi} / 计划 {p}")


if __name__ == "__main__":
    main()
