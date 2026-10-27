"""Exact and numerical matrix operations backing /math matrix.

SymPy handles rational row reduction, nullspaces, determinants and linear
systems; NumPy/SciPy handles spectral decomposition and matrix functions.
Input dimensions and symbolic complexity are bounded for group-chat use.
"""
from __future__ import annotations

import math

import numpy as np

from .math_symbolic import parse_expr


def _matrix(source:str):
    import sympy as sp
    if len(str(source))>600:
        raise ValueError("矩阵输入过长")
    rows=[]
    for line in source.split(";"):
        if not line.strip():
            raise ValueError("矩阵包含空行")
        entries=line.split(",")
        if not 1<=len(entries)<=8:raise ValueError("每行必须有 1..8 个元素，用逗号分隔")
        row=[]
        for cell in entries:
            value=parse_expr(cell)
            if not (value.is_number and value.is_finite) or value.count_ops()>12:
                raise ValueError("矩阵每个元素必须是有限的数值表达式（允许 pi、sqrt 等）")
            if abs(float(sp.N(sp.Abs(value),8)))>1e8:
                raise ValueError("矩阵元素绝对值超限")
            row.append(value)
        rows.append(row)
    if not 1<=len(rows)<=8 or len({len(r) for r in rows})!=1:
        raise ValueError("矩阵必须是 1..8 行的规则矩阵")
    return sp.Matrix(rows)


def _arr(A):
    result=np.array(A.evalf(12).tolist(),dtype=complex)
    if not np.isfinite(result).all():raise ValueError("矩阵有无效数值")
    return result


def _pretty(A):
    import sympy as sp
    if isinstance(A,sp.MatrixBase):
        return "\n".join("["+", ".join(str(z) for z in row)+"]" for row in A.tolist())
    return str(A)


def matrix_op(action:str, source:str, *, other:str|None=None, vector:str|None=None):
    import sympy as sp
    action=str(action).lower()
    A=_matrix(source)
    m,n=A.shape
    if m*n>64:raise ValueError("矩阵规模过大")
    if action in {"shape","info"}:
        return (f"size={m}x{n}\nrank={A.rank()}\n"
                f"trace={A.trace() if m==n else 'undefined'}\n"
                f"det={A.det() if m==n else 'undefined'}")
    if action=="transpose":
        return _pretty(A.T)
    if action in {"det","trace","inv","rref","null","rank","eig","svd","cond","expm","solve"}:
        pass
    elif action in {"add","mul","matmul"}:
        if not other:raise ValueError(f"{action} 需要 --b '矩阵B'")
        B=_matrix(other)
        if action=="add":
            if B.shape!=A.shape:raise ValueError("加法需要相同维度")
            return _pretty(A+B)
        if n!=B.shape[0]:raise ValueError("乘法内维度必须相同")
        return _pretty(A*B)
    else:
        raise ValueError("支持 info/shape/transpose/rank/det/trace/inv/rref/null/eig/svd/cond/expm/solve/add/mul")
    if action=="rank":
        return f"rank(A)={A.rank()}"
    if action=="rref":
        if m>6 or n>6:raise ValueError("精确行最简形矩阵尺寸最大 6x6")
        B,piv=A.rref()
        return f"RREF (pivots={piv})\n"+_pretty(B)
    if action=="null":
        if m>6 or n>6:raise ValueError("精确零空间计算矩阵尺寸最大 6x6")
        basis=A.nullspace()
        return "Nullspace basis:\n" + ("\n\n".join(_pretty(b) for b in basis) if basis else "{0}")
    if action=="solve":
        if vector is None:raise ValueError("solve 需要 --vector 'b1,b2,...'（求解 A x=b）")
        b=_matrix(vector.replace(",",";"))
        if b.shape!=(m,1):raise ValueError("b 需要与矩阵行数相等")
        if m<=6 and n<=6:
            try:
                ans=sp.linsolve((A,b))
            except ValueError as exc:raise ValueError("方程组无法求解") from exc
            return f"Solution set A*x=b: {ans}"
        M=_arr(A);vv=_arr(b).ravel()
        ans,residuals,rank,s=np.linalg.lstsq(M,vv,rcond=None)
        residual=float(np.linalg.norm(M@ans-vv))
        return f"Least squares solution (rank={rank}, residual={residual:.6g}):\n" + _pretty(sp.Matrix(ans).evalf(8))
    if m!=n and action not in {"svd","cond"}:raise ValueError(f"{action} 需要方阵")
    if action=="trace":return f"trace={A.trace()}"
    if action=="det":
        if n>5: return f"det (numerical)={np.linalg.det(_arr(A)):.10g}"
        return f"det={sp.factor(A.det())}"
    if action=="inv":
        if n<=5:
            try:return _pretty(A.inv())
            except sp.NonInvertibleMatrixError as exc:raise ValueError("矩阵奇异，无逆矩阵") from exc
        try:return _pretty(sp.Matrix(np.linalg.inv(_arr(A))).evalf(8))
        except np.linalg.LinAlgError as exc:raise ValueError("矩阵奇异，无逆矩阵") from exc
    if action=="eig":
        eigenvalues,eigenvectors=np.linalg.eig(_arr(A))
        return "Eigenvalues / normalized eigenvectors (numeric):\n"+"\n".join(
            f"λ={z:.8g}: v={np.round(eigenvectors[:,j],5).tolist()}"
            for j,z in enumerate(eigenvalues)
        )
    if action=="svd":
        U,s,Vh=np.linalg.svd(_arr(A),full_matrices=False)
        return (f"Singular values={np.round(s,9).tolist()}\n"
                f"U=\n{np.round(U,6)}\nVᴴ=\n{np.round(Vh,6)}")
    if action=="cond":return f"condition number (2-norm)={np.linalg.cond(_arr(A)):.8g}"
    if action=="expm":
        from scipy.linalg import expm
        return "exp(A)=\n"+str(np.round(expm(_arr(A)),8))
    raise ValueError("未实现的矩阵操作")
