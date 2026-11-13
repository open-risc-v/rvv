# 移植工程看板

> 由 `scripts/dashboard.py` 生成于 2026-11-13；数据源 `data/status.csv` + `data/plan.csv`。改数据，不要改这里。

## 1. 总览

| 指标 | 值 |
|---|---|
| 在册项目 | 48 |
| 门禁分布 | G0 26 / G1 8 / G2 14 / G3 0 / G4 0 / G5 0 |
| 达 G4 及以上 | 0 / 48（0%） |
| 阻塞项 | 0 |
| 超 14 天未更新 | 0 |

## 2. 按波次

| 波次 | 项目数 | 规划人日 | G4+ | 进度 |
|---|---|---|---|---|
| W1 | 6 | 90 | 0 | 0% |
| W2 | 6 | 515 | 0 | 0% |
| W3 | 10 | 515 | 0 | 0% |
| W4 | 7 | 512 | 0 | 0% |
| W5 | 14 | 518 | 0 | 0% |
| W6 | 5 | 408 | 0 | 0% |

## 3. 在册项目

| 编号 | 包 | 工程 | 优先级 | 波次 | 门禁 | 负责人 | 更新 | 阻塞 |
|---|---|---|---|---|---|---|---|---|
| RVV-001 | `media-libs/libjpeg-turbo` | `libjpeg-turbo-rvv` | P0 | W1 | G2 | - | 2026-11-13 | - |
| RVV-002 | `x11-libs/pixman` | `pixman-rvv` | P0 | W1 | G2 | - | 2026-11-13 | - |
| RVV-003 | `media-libs/libpng` | `libpng-rvv` | P0 | W1 | G2 | - | 2026-11-13 | - |
| RVV-004 | `sys-libs/zlib-ng` | `zlib-ng-rvv` | P0 | W1 | G2 | - | 2026-11-13 | - |
| RVV-005 | `dev-libs/openssl` | `openssl-rvv` | P0 | W1 | G2 | - | 2026-11-13 | - |
| RVV-006 | `dev-libs/libgcrypt` | `libgcrypt-rvv` | P1 | W1 | G2 | - | 2026-11-13 | - |
| RVV-008 | `media-libs/libwebp` | `libwebp-rvv` | P0 | W2 | G2 | - | 2026-11-13 | - |
| RVV-009 | `media-libs/libvpx` | `libvpx-rvv` | P0 | W2 | G2 | - | 2026-11-13 | - |
| RVV-010 | `media-libs/openh264` | `openh264-rvv` | P0 | W2 | G2 | - | 2026-11-13 | - |
| RVV-017 | `media-libs/opus` | `opus-rvv` | P0 | W2 | G2 | - | 2026-11-13 | - |
| RVV-018 | `media-libs/webrtc-audio-processing` | `webrtc-ap-rvv` | P0 | W2 | G2 | - | 2026-11-13 | - |
| RVV-012 | `media-libs/libaom` | `libaom-rvv` | P1 | W2 | G2 | - | 2026-11-13 | - |
| RVV-013 | `media-libs/x264` | `x264-rvv` | P1 | W3 | G1 | - | 2026-11-13 | - |
| RVV-014 | `media-libs/zimg` | `zimg-rvv` | P1 | W3 | G2 | - | 2026-11-13 | - |
| RVV-015 | `media-libs/libde265` | `libde265-rvv` | P1 | W3 | G1 | - | 2026-11-13 | - |
| RVV-026 | `dev-libs/botan` | `botan-rvv` | P1 | W3 | G1 | - | 2026-11-13 | - |
| RVV-027 | `dev-libs/crypto++` | `cryptopp-rvv` | P1 | W3 | G2 | - | 2026-11-13 | - |
| RVV-028 | `sys-cluster/ceph` | `ceph-rvv` | P1 | W3 | G1 | - | 2026-11-13 | - |
| RVV-032 | `dev-cpp/eigen` | `eigen-rvv` | P1 | W3 | G1 | - | 2026-11-13 | - |
| RVV-033 | `sci-libs/fftw` | `fftw-rvv` | P1 | W3 | G1 | - | 2026-11-13 | - |
| RVV-034 | `sci-libs/gdal` | `gdal-rvv` | P1 | W3 | G1 | - | 2026-11-13 | - |
| RVV-035 | `sci-chemistry/gromacs` | `gromacs-rvv` | P1 | W3 | G1 | - | 2026-11-13 | - |
| RVV-019 | `media-libs/speexdsp` | `speexdsp-rvv` | P1 | W4 | G0 | - | 2026-11-13 | - |
| RVV-020 | `media-libs/flac` | `flac-rvv` | P1 | W4 | G0 | - | 2026-11-13 | - |
| RVV-025 | `dev-libs/nettle` | `nettle-rvv` | P1 | W4 | G0 | - | 2026-11-13 | - |
| RVV-016 | `media-libs/x265` | `x265-rvv` | P2 | W4 | G0 | - | 2026-11-13 | - |
| RVV-029 | `net-libs/mbedtls` | `mbedtls-rvv` | P2 | W4 | G0 | - | 2026-11-13 | - |
| RVV-031 | `dev-libs/hyperscan` | `hyperscan-rvv` | P2 | W4 | G0 | - | 2026-11-13 | - |
| RVV-036 | `sci-libs/tensorflow` | `tensorflow-rvv` | P2 | W4 | G0 | - | 2026-11-13 | - |
| RVV-011 | `media-video/ffmpeg` | `ffmpeg-rvv` | P0 | W5 | G0 | - | 2026-11-13 | - |
| RVV-021 | `media-libs/openal` | `openal-soft-rvv` | P2 | W5 | G0 | - | 2026-11-13 | - |
| RVV-022 | `media-sound/mpg123` | `mpg123-rvv` | P2 | W5 | G0 | - | 2026-11-13 | - |
| RVV-023 | `media-sound/pulseaudio` | `pulseaudio-rvv` | P2 | W5 | G0 | - | 2026-11-13 | - |
| RVV-030 | `dev-libs/rocksdb` | `rocksdb-rvv` | P2 | W5 | G0 | - | 2026-11-13 | - |
| RVV-037 | `media-libs/embree` | `embree-rvv` | P2 | W5 | G0 | - | 2026-11-13 | - |
| RVV-038 | `sci-libs/pcl` | `pcl-rvv` | P2 | W5 | G0 | - | 2026-11-13 | - |
| RVV-039 | `sci-libs/dlib` | `dlib-rvv` | P2 | W5 | G0 | - | 2026-11-13 | - |
| RVV-041 | `net-libs/nodejs` | `node-rvv` | P2 | W5 | G0 | - | 2026-11-13 | - |
| RVV-043 | `dev-lang/rust` | `rust-rvv` | P3 | W5 | G0 | - | 2026-11-13 | - |
| RVV-044 | `dev-lang/go` | `go-rvv` | P3 | W5 | G0 | - | 2026-11-13 | - |
| RVV-046 | `media-libs/libsdl2` | `SDL2-rvv` | P3 | W5 | G0 | - | 2026-11-13 | - |
| RVV-047 | `games-board/stockfish` | `stockfish-rvv` | P3 | W5 | G0 | - | 2026-11-13 | - |
| RVV-048 | `app-crypt/johntheripper` | `john-rvv` | P3 | W5 | G0 | - | 2026-11-13 | - |
| RVV-007 | `media-libs/opencv` | `opencv-rvv` | P0 | W6 | G0 | - | 2026-11-13 | - |
| RVV-040 | `www-client/chromium` | `chromium-rvv` | P0 | W6 | G0 | - | 2026-11-13 | - |
| RVV-042 | `media-tv/kodi` | `kodi-rvv` | P2 | W6 | G0 | - | 2026-11-13 | - |
| RVV-024 | `media-libs/speex` | `libspeex-rvv` | P3 | W6 | G0 | - | 2026-11-13 | - |
| RVV-045 | `media-video/vlc` | `vlc-rvv` | P3 | W6 | G0 | - | 2026-11-13 | - |

