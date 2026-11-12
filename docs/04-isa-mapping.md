# 04 SSE / AVX / NEON → RVV 映射与高频坑

只列工程上真会遇到的条目。完整语义以 RVV 1.0 规范与 `__riscv_v_intrinsic` 为准。

## 1. 基础映射

| x86 | NEON | RVV 1.0（带类型后缀） | 备注 |
|---|---|---|---|
| `_mm_loadu_si128` | `vld1q_s16` | `vle16_v_i16m1` | LMUL 由元素宽度决定 |
| `_mm_storeu_si128` | `vst1q_s16` | `vse16_v_i16m1` | 尾部 agnostic |
| `_mm_add_epi16` | `vaddq_s16` | `vadd_vv_i16m1` | — |
| `_mm_adds_epi16` | `vqaddq_s16` | `vsadd_vv_i16m1` | 饱和语义一致 |
| `_mm_subs_epu8` | `vqsubq_u8` | `vssub_vv_u8m1` | 无符号饱和减 |
| `_mm_mullo_epi16` | `vmullq_s16`/`vmulq_s16` | `vmul_vv_i16m1` | 低半 |
| `_mm_mulhi_epi16` | `vmulhq_s16` | `vmulh_vv_i16m1` | 高半 |
| `_mm_madd_epi16` | `vmlal_s16` | `vwmacc_vv_i32m2` 或 `vwmul`+`vwredsum` | 注意中间宽度 32/64 |
| `_mm_sad_epu8` | `vabdq_u8`+`vpadalq` | `vwsubu`+`vwredsumu` | SAD 类首选归约 |
| `_mm_srai_epi16` | `vshrq_n_s16` | `vsra_vx_i16m1`（算术）／`vsrl`（逻辑） | 无舍入 |
| `_mm_mul_ps` | `vmulq_f32` | `vfmul_vv_f32m2` | f32 用 m2 拿 8+ lane |
| `_mm_dp_ps` | `vmlaq`+`vpadd` | `vfmul`+`vfredusum` | 归约顺序不确定，浮点不可 bit-exact |
| `_mm_set1_*` | `vdupq_n_*` | `vmv_v_x_*` / `vfmv_v_f_*` | 广播便宜 |
| `_mm_cmpgt_*` | `vcgtq_*` | `vmsgt_vv_*_b*` | 结果进掩码寄存器 |
| `_mm_blendv_*` | `vbslq_*` | `vmerge_vvm_*` | ⚠️ gcc 操作数序与规范相反 |
| `_mm_abs_epi16` | `vabsq_s16` | `vabs_v_i16m1` | — |
| `_mm_min/max_epi32` | `vminq/vmaxq` | `vmin_vv`/`vmax_vv` | 有符号；无符号用 `_u` |

## 2. 困难映射（工作量与风险集中在这里）

| 操作 | x86 / NEON | RVV 现状 | 工程对策 |
|---|---|---|---|
| **打包窄化** | `packsswb` / `vqmovn` | `vnclip_wx`（受 `vxrm` 舍入影响）→ 用 `vsra`+`vncvt` 精确复现 | 打包两个寄存器成一次操作在本架构不存在，需 `vnsrl`+`vslideup`/`vrgather` 拼接；**优先改布局避免打包** |
| **字节洗牌** | `pshufb` / `vqtbl1q` | `vrgather_vv`（单指令，但成本高，vlen 大时尤其） | 一般 1 次 `vrgather` ≈ 2–4 条算术指令的成本；查表类算法可考虑 `vluxei` 或重排数据 |
| **水平归约** | `hadd` / `vpadd` | `vredsum/vredmin/vredmax`（仅一次） | 多次水平归约 = 反模式；改 entry 并行 |
| **跨 128-bit lane 置换** | `permute2x128` | 无直接对应 | 拆成多 LMUL 组 + `vrgather`，或改数据布局 |
| **位掩码化** | `movemask` | `vmseq` → `vfirst`/`vcpop`（掩码寄存器） | 比 x86 便宜，但注意 `vfirst` 返回的是"第一个置位下标" |
| **收集/散播** | `gather`/`scatter` | `vluxei32/vsuxei32`（索引必须是 32/64 位） | 8/16 位索引需先扩宽，成本高；能改布局就别 gather |
| **整数除法** | 无（编译器展开） | 无向量除 | 走定点倒数（`vdivu` 不存在），用查表+乘法 |
| **AES / GHASH** | `aesenc` / `pclmulqdq` | `zvkned`（`vaesef/vaesem`）、`zvbc`（`vclmul`） | 没有扩展就退回标量查表（T-table 不安全）/ bitsliced 实现 |
| **CRC32** | `crc32` 指令（SSE4.2） | `zbc` 的 `vcrc32` 系列，或查表 | `zlib-ng`/`ceph` 已用 `crc32_zbc`，直接接 |
| **饱和双倍乘高** | `vqdmulh` | 无单指令 | `vwmul` + `vsra` + 手写饱和 |
| **定点转浮点** | `cvt` | `vfcvt_x_f_v` + `vxrm` | 舍入模式必须显式设定，否则与 x86 默认不同 |

## 3. 七个必踩的坑（每条都在真实项目里出过）

1. **`vsetvl` 位置**：必须循环体第一句。忘写 = 未初始化 `vl` = `n` 永不归零 = 板上 100% CPU 死循环，
   而 qemu 可能"看起来能跑"。
2. **`vmerge` 操作数序**：gcc 按汇编序 `(vd, vs2, vs1, v0)`，C 语义是 `m ? op2 : op1` 的反向。
   用已知值双分支单测固定。
3. **`vredsum/vredmax` 参数序**：`(向量, 标量载体)`，clang 与 gcc 相反。
4. **尾部 agnostic**：短 VL 写的尾部是 indeterminate。跨操作读取 = 源码正确性问题。
   持久累加器用 `_tu`；归约只在活跃 VL 上做。
5. **掩码类型不是"每元素 1 bit"**：`vbool8_t` = SEW/LMUL = 8；比较内建必须带 `vl`。
6. **数组元素不能是 RVV 向量类型**（gcc-13 报错）：向量列必须先落到标量缓冲再 `vle` 重载，
   或改成"一 lane 一 entry"的无临时数组写法。
7. **`vlse` 的 stride 单位是字节**，且实测比 `vle` 慢 3.7–4.7 倍（X60/X100）。
   **数据布局优化（转置一次）通常比跨步加载更值钱**。

## 4. RVV 相对 x86 的结构性优势（设计时要主动用）

- **长度无关**：同一内核在 VLEN=128/256/512/1024 上都能跑，不用维护 3 套 SSE/AVX512 代码；
  但也意味着**不能靠"寄存器宽度"做分块参数**，要改成运行时 `vsetvlmax`。
- **掩码是一等公民**：尾块、条件更新不需要"补零 + 事后修正"，但要注意掩码寄存器压力
  （32 个 `v0–v31` 里掩码占独立的 32 个，不是共用）。
- **段加载/段存储**：`vlseg2e16/vsseg2e16` 天然对应 NEON 的 `vld2/vst2` 与图像的交错格式，
  是图像/音频类的免费午餐（要求 gcc-14+ 的元组类型）。
- **LMUL**：`m1/m2/m4/m8` 是可调的"寄存器组宽度"，比 x86 的固定宽度更灵活，
  但也是最大的性能杠杆与最大的正确性风险（`vbool`/`SEW` 全跟着变）。

## 5. 选型建议（按包类型）

| 包类型 | 建议 LMUL 起点 | 理由 |
|---|---|---|
| 8/16 位图像、音频 | `e16m2` / `e8m2` | 兼顾 lane 数与寄存器压力 |
| 32 位整数（索引、累加） | `e32m2` | 点积/直方图常用 |
| 浮点 f32 | `f32m2`（GEMM 用 `m4`） | 与 x86 的 256-bit 对齐 |
| 归约/扫描 | `m1` + 载体 | 减少 `vredsum` 的宽度转换开销 |
