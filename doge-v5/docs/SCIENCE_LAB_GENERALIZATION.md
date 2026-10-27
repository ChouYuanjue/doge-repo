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

## 功能审计

| 命令 | 本轮状态 | 算法与自由度 |
|---|---|---|
| `/math calc/simplify/expand/factor/solve/diff/integrate/limit` | 保留真实算法 | 原有 SymPy 计算，有表达式输入 |
| `/math numeric/base/pi/prime/factorint/stats/oeis/wa` | 保留真实算法 | 实际计算或真实外部查询 |
| `/math matrix` | **新增** | 任意维度有界矩阵的精确及数值线性代数 |
| `/math formal` | 明确有限功能 | 仅形式化助手/外部入口，不宣称本地 Lean/Coq 证明 |
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
| `/lab ulam/modcircle/penrose` | 保留实算法 | 真正的素数螺旋、模乘连线、Penrose 细分 |
| `/lab bloch/relativity` | 保留特定物理模型 | 单量子比特纯态和 Lorentz 变换，可调角度/速度 |
| `/lab moire/sandpile` | 保留真实数值演示 | 干涉条纹/沙堆崩塌，属于特定模型而非任意 PDE |
| `/lab lens/well/diffraction` | 保留有界解析模型 | 薄透镜、无限深势阱、双缝 Fraunhofer 衍射 |
| `/lab beats/chladni/phyllotaxis` | 保留教学模型 | 任意拍频、方形板模态近似、植序角等；Chladni 不应称严格有限元求解 |

## 计算范围和不可夸大部分

- 复函数及 Newton 运算支持有限白名单，未实现任意 Python/自定义函数定义；有奇点时明确标出无效值。
- 黑色逃逸时间像素表示“迭代限额内尚未逃逸”，**不构成数学证明**；自定义映射未必有严格的 Julia/Mandelbrot 集定义。
- SciPy 数值 ODE、波动、混沌、SIR、Ising 等是理论模型的计算，**不是真实实验测量**。求解器存在精度/稳定性与计算预算限制。
- `/lab xrd` 使用**常数散射权重的理想运动学结构因子**，不含元素随角度变化的 form factor、温度因素、吸收/仪器函数等；真实 CIF 粉末谱使用 `/mat crystal powder` 对接的现有专业库。
- `/lab orbital` 是**氢样无电子关联、原子单位解析波函数**，不直接解决多电子原子/分子的电子结构。
- `/lab knot` 只绘制三维曲线，未计算 Jones/Alexander 多项式、交叉数或同痕证明。
- `/lab chladni` 仍是平方板模态近似，不宣称任意边界弹性板求解。
- `/lab life`、DLA、其他旧演示仅提供其具体数学模型。此类模型本身有限，但输入和数值演化不是硬编码图片。
- 保留原有快捷命令参数，并统一在 `/help lab` 中展示更多样例；未知选项直接报错，避免伪装成接受参数。

## 测试与部署

- `tests/test_science_generalization.py`：注入/非法参数拒绝，任意函数矩阵，渲染实输出，不同方程和晶格产生不同图片，帮助系统回归。
- `tests/test_math_rrpl_life.py`、`tests/test_parameter_semantics.py`：兼容现存数学与元胞自动机行为。
- 重启 `doge-astrbot.service` 才会刷新 Python 模块缓存；`doge-runtime/data/plugins` 到 Git 源码为符号链接。
- 使用 `journalctl -u doge-astrbot.service`、`systemctl is-active doge-astrbot.service` 验证重新加载。
