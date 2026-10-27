# Doge Math / Lab 通用化与真实性审计

> 本文档对应 2026-10-28 server10 的科学功能修复。**预设是一种输入简写，功能是否真实取决于参数能否参与底层计算，而不是预设数量。**

## 组件与实际计算后端

- `science_expression.py`：限定 AST（常量、变量、四则运算、幂、批准的数学函数），编译成 SymPy 表达式，数值求值由 NumPy 执行；不允许任意 Python 程序。复杂度、指数和图像尺寸有上限。
- `math_matrices.py`：SymPy 精确行化简、核空间、求逆和代数方程组；NumPy/SciPy 做 SVD、条件数、特征分解、矩阵指数及最小二乘。
- `visual_lab_analytic.py`：复平面域着色、Newton 收敛域、逃逸时间迭代、函数/参数曲线、FFT、矩阵变换、氢原子解析轨道。
- `visual_lab_dynamics.py`：SciPy 常微分方程求解；离散映射、分岔、任意点电荷/向量场、L-system、速度 Verlet N 体、Gray-Scott 反应扩散、Voronoi、元胞自动机。
- `visual_lab_stochastic.py`：可设随机种子的 Ising、site/bond 渗流、随机矩阵、Galton、布朗运动、广义蚂蚁。
- `visual_lab_models.py`：可设质量/长度/初值的双摆、任意相干点波源、SIR、捕食者—猎物模型、复制子动力学，以及参数结/曲线。
- `visual_lab_crystals.py`：任意三维晶格基矢、分数位置基底、倒格子、Bragg 几何及简化的运动学结构因子。
- `visual_lab_plate.py`、`visual_lab_pde.py`：**scikit-fem 12.0.2** 真正装配薄板四阶弯曲特征值问题、Poisson/热方程/膜振动有限元，支持方形、圆盘、L 形区域和边界/网格参数。
- `math_knot.py`、`math_knot_worker.py`：**KnotPy** (`b5fcf1a`，BSD-3-Clause) 对结名或任意 PD 平面图计算 Jones/Alexander 多项式；通过 **bubblewrap** 在低权限、无网络、独立 CPU/内存/超时限制进程中执行。
- `visual_lab_quantum_optics.py`：任意 1D 有限势函数的稀疏 Schrödinger 数值本征问题、任意复透过率光阑远场 FFT、组合薄透镜 ABCD 光线追迹。
- `visual_lab_remaining.py`：混态密度矩阵与酉量子门、Lorentz 事件变换、不变量与沙堆真正稳定化。
- `visual_lab_patterns.py`：双光栅 Moiré、参数化植序、多音叠加、任意整数步长素数螺旋与非线性模圆映射。

## 功能审计

| 命令 | 本轮状态 | 算法与自由度 |
|---|---|---|
| `/math calc/simplify/expand/factor/solve/diff/integrate/limit` | 保留真实算法 | 原有 SymPy 计算，有表达式输入 |
| `/math numeric/base/pi/prime/factorint/stats/oeis/wa` | 保留真实算法 | 实际计算或真实外部查询 |
| `/math matrix` | **新增** | 任意维度有界矩阵的精确及数值线性代数 |
| `/math formal` | 明确有限功能 | 仅形式化助手/外部入口，不宣称本地 Lean/Coq 证明；2026-10-28 官方 Lean 下载入口因 server10 连接 GitHub 失败，未获得本地 kernel |
| `/math knot` | **新增真实结不变量** | KnotPy 从结名或任意 PD 图计算 Alexander、Jones 多项式和 determinant；第三方计算被 sandbox 隔离 |
| `/lab complex/domain` | **重构** | 任意复表达式，不限少数内置函数 |
| `/lab newton` | **重构** | 任意可微复表达式、自动求导、阈值/迭代控制 |
| `/lab fractal mandelbrot/julia` | **重构** | 任意二元迭代式 z↦f(z,c)、任意中心和迭代上限 |
| `/lab chaos bifurcation` | **重构** | 任意 x↦f(x,r)，可配置参数扫描和预热 |
| `/lab linear` | **重构** | 2–8 维非方阵/方阵的可视化与数值谱 |
| `/lab plot/param` | **新增** | 任意合法实函数和任意二维/三维参数曲线 |
| `/lab spectrum` | **重构** | 任意时间表达式 + 实际 FFT；方/锯齿波使用 SciPy |
| `/lab orbital` | **重构** | SciPy 球谐与径向函数，合法任意 n,l,m |
| `/lab ode/map` | **新增** | 自定义状态方程、初值、参数、求解区间 |
| `/lab attractor` | **重构** | Lorenz/Rössler/Clifford 仅是通用引擎预设 |
| `/lab wave/field` | **重构** | 任意多个波源/点电荷，或任意安全向量场 |
| `/lab pendulum/orbit/nbody` | **重构** | 任意双摆物理量，以及任意 2–6 体初态/质量 |
| `/lab reaction` | **重构** | Gray–Scott 四个参数、步数、尺寸、种子可调 |
| `/lab lsys` | **重构** | 完整有界字符串替换文法、分支 turtle |
| `/lab ca` | **重构** | 任意初等 CA 规则/位串/边界/随机初态 |
| `/lab ising/percolation` | **重构** | 温度/外场/耦合、site/bond、概率与 RNG |
| `/lab randommatrix` | **重构** | Ginibre/GOE/GUE/Wishart 任意种子及规模 |
| `/lab galton/brownian/ant` | **重构** | 偏置概率/扩散与漂移/多状态转向规则 |
| `/lab voronoi` | **重构** | 用户给出真实点集或随机生成种子 |
| `/lab lattice/xrd` | **重构** | 任意三维晶格和基底，计算倒格子/简化结构因子 |
| `/lab knot/lissajous` | **重构** | 三维参数曲线、频率与相位，不将可视化称为结认证 |
| `/lab sir/predator/replicator` | **重构** | SciPy 求解用户可配置生物动力学/博弈矩阵 |
| `/lab life` | **修正** | B/S 规则的出生与存活分开；支持 RLE、cells、random:seed:density 和状态接续 |
| `/lab dla` | **增强** | 种子、粒子数、网格、4/8 邻接可设 |
| `/lab ulam/modcircle/penrose` | **扩展 Ulam/模圆** | 自定义素数起点/步长与任意安全模映射，Penrose 继续使用真实三角形细分 |
| `/lab pde` | **新增有限元计算** | 任意解析源项的 2D Poisson、带任意初值的热扩散及 Laplace 膜本征模态；支持方形、圆形与 L 形网格 |
| `/lab bloch/relativity` | **重构** | 用户给定任意合法 2×2 密度矩阵并按序施加酉门，计算 Bloch 向量与 purity；任意 1+1 事件 Lorentz 变换与间隔守恒 |
| `/lab moire/sandpile` | **重构** | 双光栅各自周期/相位/角度可调；沙堆支持任意多点投放、边界和吸收点，达到稳定态才返回成功 |
| `/lab lens/well/diffraction` | **重构** | 多透镜 ABCD 矩阵与任意初始光线、任意有限 V(x) 的 Schrödinger 数值本征态、任意 1D 复光阑 FFT 衍射 |
| `/lab beats/chladni/phyllotaxis` | **重构** | 多音频率/幅度/相位叠加、scikit-fem 薄板振动真实数值本征模态、带增长指数与随机扰动的植序几何 |

## 计算范围和不可夸大部分

- 复函数及 Newton 运算支持有限白名单，未实现任意 Python/自定义函数定义；有奇点时明确标出无效值。
- 黑色逃逸时间像素表示“迭代限额内尚未逃逸”，**不构成数学证明**；自定义映射未必有严格的 Julia/Mandelbrot 集定义。
- SciPy 数值 ODE、波动、混沌、SIR、Ising 等是理论模型的计算，**不是真实实验测量**。求解器存在精度/稳定性与计算预算限制。
- `/lab xrd` 使用**常数散射权重的理想运动学结构因子**，不含元素随角度变化的 form factor、温度因素、吸收/仪器函数等；真实 CIF 粉末谱使用 `/mat crystal powder` 对接的现有专业库。
- `/lab orbital` 是**氢样无电子关联、原子单位解析波函数**，不直接解决多电子原子/分子的电子结构。
- `/lab knot` 仍只绘制用户给定的三维参数曲线。严肃的结论请将命名结或 PD 结图传给 `/math knot`；它确实算 Jones/Alexander，但不能仅靠多项式证明同痕或判定所有结的类型。
- `/lab chladni` 使用 Morley 离散单元求真实 Kirchhoff–Love 薄板数值振型，支持有限种区域和边界。它尚未模拟实际沙粒、驱动、阻尼、有限厚度或任意 CAD 几何；混合两个不同频率振型是瞬时叠加，不是单一驻波。
- `/lab pde` 支持限定形状与齐次 Dirichlet 边界下的线性二维方程，不等于任意 PDE/任意边界条件的通用 FEM 框架；必须通过网格加密验证收敛性。
- `/lab well` 的任意势也只在有限区间齐次 Dirichlet 盒子中求离散数值谱，不能直接视为真实原子或分子实验。
- `/lab diffraction` 是单维标量 Fraunhofer 远场模型；ABCD 透镜只在近轴近似内成立。
- `/lab life`、DLA、其他旧演示仅提供其具体数学模型。此类模型本身有限，但输入和数值演化不是硬编码图片。
- 保留原有快捷命令参数，并统一在 `/help lab` 中展示更多样例；未知选项直接报错，避免伪装成接受参数。

## 测试与部署

- `tests/test_science_generalization.py`：注入/非法参数拒绝，任意函数矩阵，渲染实输出，不同方程和晶格产生不同图片，帮助系统回归。
- `tests/test_science_remaining.py`：12 组真实非 demo 结果/物理性质测试（结的 determinant、方势阱能级、PDE/薄板变化、Lorentz 守恒、密度矩阵、沙堆完全稳定等）。
- `tools/install_science_backends.sh`：固定版本科学依赖和 KnotPy 指定 Git SHA；仅对已审计的 import typo 作最小补丁，提供符号不变量安装自检。
- `tests/test_math_rrpl_life.py`、`tests/test_parameter_semantics.py`：兼容现存数学与元胞自动机行为。
- 重启 `doge-astrbot.service` 才会刷新 Python 模块缓存；`doge-runtime/data/plugins` 到 Git 源码为符号链接。
- 使用 `journalctl -u doge-astrbot.service`、`systemctl is-active doge-astrbot.service` 验证重新加载。
