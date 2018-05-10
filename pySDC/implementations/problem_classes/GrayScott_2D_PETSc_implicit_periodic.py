from __future__ import division
import numpy as np
import time
from petsc4py import PETSc

from pySDC.core.Problem import ptype
from pySDC.core.Errors import ParameterError


class GS(object):

    def __init__(self, da, params, factor, dx, dy, L):
        assert da.getDim() == 2
        self.da = da
        self.params = params
        self.factor = factor
        self.dx = dx
        self.dy = dy
        self.L = L
        self.localX = da.createLocalVec()

    def formFunction(self, snes, X, F):
        #
        self.da.globalToLocal(X, self.localX)
        x = self.da.getVecArray(self.localX)
        f = self.da.getVecArray(F)
        mx, my = self.da.getSizes()
        (xs, xe), (ys, ye) = self.da.getRanges()
        for j in range(ys, ye):
            for i in range(xs, xe):
                # u_e = u_w = u_n = u_s = [0.0, 0.0]
                u = x[i, j]  # center
                # if i < mx - 1: u_e = x[i + 1, j]  # east
                # if i > 0: u_w = x[i - 1, j]  # west
                # if j < my - 1: u_s = x[i, j + 1]  # south
                # if j > 0: u_n = x[i, j - 1]  # north
                u_e = x[i + 1, j]  # east
                u_w = x[i - 1, j]  # west
                u_s = x[i, j + 1]  # south
                u_n = x[i, j - 1]  # north
                u_xx = (u_e - 2 * u + u_w)
                u_yy = (u_n - 2 * u + u_s)
                f[i, j, 0] = x[i, j, 0] - (self.factor * (self.params.Du * (u_xx[0] / self.dx ** 2 + u_yy[0] / self.dy ** 2) -
                        x[i, j, 0] * x[i, j, 1] ** 2 + self.params.A * (1 - x[i, j, 0])))
                f[i, j, 1] = x[i, j, 1] - (self.factor * (self.params.Dv * (u_xx[1] / self.dx ** 2 + u_yy[1] / self.dy ** 2) +
                        x[i, j, 0] * x[i, j, 1] ** 2 - self.params.B * x[i, j, 1]))

    def formJacobian(self, snes, X, J, P):
        #
        t0 = time.time()
        self.da.globalToLocal(X, self.localX)
        x = self.da.getVecArray(self.localX)
        P.zeroEntries()
        row = PETSc.Mat.Stencil()
        col = PETSc.Mat.Stencil()
        mx, my = self.da.getSizes()
        (xs, xe), (ys, ye) = self.da.getRanges()
        for j in range(ys, ye):
            for i in range(xs, xe):
                row.index = (i, j)
                col.index = (i, j)
                row.field = 0
                col.field = 0
                P.setValueStencil(row, col, 1.0 - self.factor * (self.params.Du * (-2.0 / self.dx ** 2 - 2.0 / self.dy ** 2) -x[i, j, 1] ** 2 - self.params.A))
                row.field = 0
                col.field = 1
                P.setValueStencil(row, col, self.factor * 2.0 * x[i, j, 0] * x[i, j, 1])
                row.field = 1
                col.field = 1
                P.setValueStencil(row, col, 1.0 - self.factor * (self.params.Dv * (-2.0 / self.dx ** 2 - 2.0 / self.dy ** 2) + 2.0 * x[i, j, 0] * x[i, j, 1] - self.params.B))
                row.field = 1
                col.field = 0
                P.setValueStencil(row, col, -self.factor * x[i, j, 1] ** 2)
                col.index = (i, j - 1)
                col.field = 0
                row.field = 0
                P.setValueStencil(row, col, -self.factor * self.params.Du / self.dy ** 2)
                col.field = 1
                row.field = 1
                P.setValueStencil(row, col, -self.factor * self.params.Dv / self.dy ** 2)
                # if j < my - 1:
                col.index = (i, j + 1)
                col.field = 0
                row.field = 0
                P.setValueStencil(row, col, -self.factor * self.params.Du / self.dy ** 2)
                col.field = 1
                row.field = 1
                P.setValueStencil(row, col, -self.factor * self.params.Dv / self.dy ** 2)
                # if i > 0:
                col.index = (i - 1, j)
                col.field = 0
                row.field = 0
                P.setValueStencil(row, col, -self.factor * self.params.Du / self.dx ** 2)
                col.field = 1
                row.field = 1
                P.setValueStencil(row, col, -self.factor * self.params.Dv / self.dx ** 2)
                # if i < mx - 1:
                col.index = (i + 1, j)
                col.field = 0
                row.field = 0
                P.setValueStencil(row, col, -self.factor * self.params.Du / self.dx ** 2)
                col.field = 1
                row.field = 1
                P.setValueStencil(row, col, -self.factor * self.params.Dv / self.dx ** 2)

        P.assemble()
        # P = self.L - self.factor * P
        if J != P:
            J.assemble()  # matrix-free operator
        print(time.time() - t0)
        return PETSc.Mat.Structure.SAME_NONZERO_PATTERN


# noinspection PyUnusedLocal
class petsc_grayscott(ptype):
    """

    """

    def __init__(self, problem_params, dtype_u, dtype_f):
        """
        Initialization routine

        Args:
            problem_params: custom parameters for the example
            dtype_u: particle data type (will be passed parent class)
            dtype_f: acceleration data type (will be passed parent class)
        """

        # define the Dirichlet boundary
        if 'comm' not in problem_params:
            problem_params['comm'] = PETSc.COMM_WORLD
        if 'sol_tol' not in problem_params:
            problem_params['sol_tol'] = 1E-10
        if 'sol_maxiter' not in problem_params:
            problem_params['sol_maxiter'] = None

        # these parameters will be used later, so assert their existence
        essential_keys = ['nvars', 'Du', 'Dv', 'A', 'B']
        for key in essential_keys:
            if key not in problem_params:
                msg = 'need %s to instantiate problem, only got %s' % (key, str(problem_params.keys()))
                raise ParameterError(msg)

        da = PETSc.DMDA().create([problem_params['nvars'][0], problem_params['nvars'][1]], dof=2, boundary_type=3,
                                 stencil_width=1,
                                 comm=problem_params['comm'])

        # invoke super init, passing number of dofs, dtype_u and dtype_f
        super(petsc_grayscott, self).__init__(init=da, dtype_u=dtype_u, dtype_f=dtype_f, params=problem_params)

        # compute dx, dy and get local ranges
        self.dx = 100.0 / (self.params.nvars[0])
        self.dy = 100.0 / (self.params.nvars[1])
        (self.xs, self.xe), (self.ys, self.ye) = self.init.getRanges()

        # compute discretization matrix A and identity
        self.A = self.__get_A()
        self.Id = self.__get_Id()
        self.localX = self.init.createLocalVec()

        # setup solver
        self.snes = PETSc.SNES()
        self.snes.create(comm=self.params.comm)
        # self.snes.getKSP().setType('cg')
        # self.snes.setType('ngmres')
        self.snes.setFromOptions()
        self.snes.setTolerances(rtol=self.params.sol_tol, atol=self.params.sol_tol, stol=self.params.sol_tol, max_it=self.params.sol_maxiter)

    def __get_A(self):
        """
        Helper function to assemble PETSc matrix A

        Returns:
            PETSc matrix object
        """
        A = self.init.createMatrix()
        A.setType('aij')  # sparse
        A.setFromOptions()
        A.setPreallocationNNZ((5, 5))
        A.setUp()

        A.zeroEntries()
        row = PETSc.Mat.Stencil()
        col = PETSc.Mat.Stencil()
        mx, my = self.init.getSizes()
        (xs, xe), (ys, ye) = self.init.getRanges()
        for j in range(ys, ye):
            for i in range(xs, xe):
                row.index = (i, j)
                row.field = 0
                A.setValueStencil(row, row, self.params.Du * (-2.0 / self.dx ** 2 - 2.0 / self.dy ** 2))
                row.field = 1
                A.setValueStencil(row, row, self.params.Dv * (-2.0 / self.dx ** 2 - 2.0 / self.dy ** 2))
                # if j > 0:
                col.index = (i, j - 1)
                col.field = 0
                row.field = 0
                A.setValueStencil(row, col, self.params.Du / self.dy ** 2)
                col.field = 1
                row.field = 1
                A.setValueStencil(row, col, self.params.Dv / self.dy ** 2)
                # if j < my - 1:
                col.index = (i, j + 1)
                col.field = 0
                row.field = 0
                A.setValueStencil(row, col, self.params.Du / self.dy ** 2)
                col.field = 1
                row.field = 1
                A.setValueStencil(row, col, self.params.Dv / self.dy ** 2)
                # if i > 0:
                col.index = (i - 1, j)
                col.field = 0
                row.field = 0
                A.setValueStencil(row, col, self.params.Du / self.dx ** 2)
                col.field = 1
                row.field = 1
                A.setValueStencil(row, col, self.params.Dv / self.dx ** 2)
                # if i < mx - 1:
                col.index = (i + 1, j)
                col.field = 0
                row.field = 0
                A.setValueStencil(row, col, self.params.Du / self.dx ** 2)
                col.field = 1
                row.field = 1
                A.setValueStencil(row, col, self.params.Dv / self.dx ** 2)
        A.assemble()

        return A

    def __get_Id(self):
        """
        Helper function to assemble PETSc identity matrix

        Returns:
            PETSc matrix object
        """

        Id = self.init.createMatrix()
        Id.setType('aij')  # sparse
        Id.setFromOptions()
        Id.setPreallocationNNZ((1, 1))
        Id.setUp()

        Id.zeroEntries()
        row = PETSc.Mat.Stencil()
        mx, my = self.init.getSizes()
        (xs, xe), (ys, ye) = self.init.getRanges()
        for j in range(ys, ye):
            for i in range(xs, xe):
                for indx in [0, 1]:
                    row.index = (i, j)
                    row.field = indx
                    Id.setValueStencil(row, row, 1.0)

        Id.assemble()

        return Id

    def eval_f(self, u, t):
        """
        Routine to evaluate the RHS

        Args:
            u (dtype_u): current values
            t (float): current time

        Returns:
            dtype_f: the RHS
        """

        f = self.dtype_f(self.init)
        self.A.mult(u.values, f.values)

        fa = self.init.getVecArray(f.values)
        xa = self.init.getVecArray(u.values)
        for i in range(self.xs, self.xe):
            for j in range(self.ys, self.ye):
                fa[i, j, 0] += -xa[i, j, 0] * xa[i, j, 1] ** 2 + self.params.A * (1 - xa[i, j, 0])
                fa[i, j, 1] += xa[i, j, 0] * xa[i, j, 1] ** 2 - self.params.B * xa[i, j, 1]

        return f

    def solve_system(self, rhs, factor, u0, t):
        """
        Simple linear solver for (I-factor*A)u = rhs

        Args:
            rhs (dtype_f): right-hand side for the linear system
            factor (float): abbrev. for the local stepsize (or any other factor required)
            u0 (dtype_u): initial guess for the iterative solver
            t (float): current time (e.g. for time-dependent BCs)

        Returns:
            dtype_u: solution as mesh
        """

        me = self.dtype_u(u0)
        target = GS(self.init, self.params, factor, self.dx, self.dy, self.Id - factor * self.A)

        F = self.init.createGlobalVec()
        self.snes.setFunction(target.formFunction, F)
        J = self.init.createMatrix()
        self.snes.setJacobian(target.formJacobian, J)

        self.snes.solve(rhs.values, me.values)

        print( self.snes.getConvergedReason(), self.snes.getLinearSolveIterations(), self.snes.getFunctionNorm(), self.snes.getKSP().getResidualNorm() )
        # exit()

        return me

    def u_exact(self, t):
        """
        Routine to compute the exact solution at time t

        Args:
            t (float): current time

        Returns:
            dtype_u: exact solution
        """

        me = self.dtype_u(self.init)
        xa = self.init.getVecArray(me.values)
        for i in range(self.xs, self.xe):
            for j in range(self.ys, self.ye):
                xa[i, j, 0] = 1.0 - 0.5 * np.power(np.sin(np.pi * i * self.dx / 100) *
                                                   np.sin(np.pi * j * self.dy / 100), 100)
                xa[i, j, 1] = 0.25 * np.power(np.sin(np.pi * i * self.dx / 100) *
                                              np.sin(np.pi * j * self.dy / 100), 100)

        return me