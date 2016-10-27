from __future__ import division

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as LA

from pySDC.Problem import ptype


class generalized_fisher(ptype):
    """
    Example implementing the unforced 1D heat equation with Dirichlet-0 BC in [0,1]

    Attributes:
        A: second-order FD discretization of the 1D laplace operator
        dx: distance between two spatial nodes
    """

    def __init__(self, cparams, dtype_u, dtype_f):
        """
        Initialization routine

        Args:
            cparams: custom parameters for the example
            dtype_u: mesh data type (will be passed parent class)
            dtype_f: mesh data type (will be passed parent class)
        """

        # these parameters will be used later, so assert their existence
        assert 'nvars' in cparams
        assert 'nu' in cparams
        assert 'lambda0' in cparams
        assert 'maxiter' in cparams
        assert 'newton_tol' in cparams

        assert (cparams['nvars'] + 1) % 2 == 0

        # invoke super init, passing number of dofs, dtype_u and dtype_f
        super(generalized_fisher, self).__init__(self.nvars, dtype_u, dtype_f)

        # compute dx and get discretization matrix A
        self.dx = 2.0 / (self.nvars + 1)
        self.A = self.__get_A(self.nvars, self.dx)

    def __get_A(self, N, dx):
        """
        Helper function to assemble FD matrix A in sparse format

        Args:
            N: number of dofs
            nu: diffusion coefficient
            dx: distance between two spatial nodes

        Returns:
         matrix A in CSC format
        """

        stencil = [1, -2, 1]
        A = sp.diags(stencil, [-1, 0, 1], shape=(N+2, N+2), format='lil')
        A *= 1.0 / (dx ** 2)

        return A

    def solve_system(self, rhs, factor, u0, t):
        """
        Simple Newton solver

        Args:
            rhs: right-hand side for the linear system
            factor: abbrev. for the node-to-node stepsize (or any other factor required)
            u0: initial guess for the iterative solver (not used here so far)
            t: current time (e.g. for time-dependent BCs)

        Returns:
            solution as mesh
        """

        u = self.dtype_u(u0)

        nu = self.params.nu
        lambda0 = self.params.lambda0

        lam1 = lambda0 / 2.0 * ((nu / 2.0 + 1) ** 0.5 + (nu / 2.0 + 1) ** (-0.5))
        sig1 = lam1 - np.sqrt(lam1 ** 2 - lambda0 ** 2)
        ul = (1 + (2 ** (nu / 2.0) - 1) * np.exp(-nu / 2.0 * sig1 * (-1 + 2 * lam1 * t))) ** (-2.0 / nu)
        ur = (1 + (2 ** (nu / 2.0) - 1) * np.exp(-nu / 2.0 * sig1 * (1 + 2 * lam1 * t))) ** (-2.0 / nu)

        # start newton iteration
        n = 0
        while n < self.params.maxiter:

            # form the function g with g(u) = 0
            uext = np.concatenate(([ul], u.values, [ur]))
            g = u.values - \
                factor * (self.A.dot(uext)[1:-1] + lambda0 ** 2 * u.values * (1 - u.values ** nu)) - rhs.values

            # if g is close to 0, then we are done
            res = np.linalg.norm(g, np.inf)

            if res < self.newton_tol:
                break

            # assemble dg
            dg = sp.eye(self.nvars) - \
                 factor * (self.A[1:-1, 1:-1] + sp.diags(lambda0 ** 2 - lambda0 ** 2 * (nu + 1) * u.values ** nu))

            # newton update: u1 = u0 - g/dg
            u.values -= LA.spsolve(dg, g)

            # increase iteration count
            n += 1

        return u

    def eval_f(self, u, t):
        """
        Routine to evaluate the RHS

        Args:
            u: current values
            t: current time

        Returns:
            the RHS
        """

        lam1 = self.params.lambda0 / 2.0 * ((self.params.nu / 2.0 + 1) ** 0.5 + (self.params.nu / 2.0 + 1) ** (-0.5))
        sig1 = lam1 - np.sqrt(lam1 ** 2 - self.params.lambda0 ** 2)
        ul = (1 + (2 ** (self.params.nu / 2.0) - 1) *
                     np.exp(-self.params.nu / 2.0 * sig1 * (-1 + 2 * lam1 * t))) ** (-2.0 / self.params.nu)
        ur = (1 + (2 ** (self.params.nu / 2.0) - 1) *
                     np.exp(-self.params.nu / 2.0 * sig1 * (1 + 2 * lam1 * t))) ** (-2.0 / self.params.nu)

        uext = np.concatenate(([ul], u.values, [ur]))

        f = self.dtype_f(self.nvars)
        f.values = self.A.dot(uext)[1:-1] + self.params.lambda0 ** 2 * u.values * (1 - u.values ** self.params.nu)
        return f

    def u_exact(self, t):
        """
        Routine to compute the exact solution at time t

        Args:
            t: current time

        Returns:
            exact solution
        """

        me = self.dtype_u(self.nvars)
        xvalues = np.array([(i + 1 - (self.nvars+1) / 2) * self.dx for i in range(self.nvars)])

        lam1 = self.params.lambda0 / 2.0 * ((self.params.nu / 2.0 + 1) ** 0.5 + (self.params.nu / 2.0 + 1) ** (-0.5))
        sig1 = lam1 - np.sqrt(lam1 ** 2 - self.params.lambda0 ** 2)
        me.values = (1 + (2 ** (self.params.nu / 2.0) - 1) *
                     np.exp(-self.params.nu / 2.0 * sig1 * (xvalues + 2 * lam1 * t))) ** (-2.0 / self.params.nu)
        return me

    def eval_jacobian(self, u):

        dfdu = self.A[1:-1, 1:-1] + sp.diags(self.params.lambda0 ** 2 - self.params.lambda0 ** 2 * (self.params.nu + 1) *
                                           u.values ** self.params.nu)

        return dfdu

    def solve_system_jacobian(self, dfdu, rhs, factor, u0, t):
        """
        Simple linear solver for (I-dtA)u = rhs

        Args:
            dfdu: the Jacobian of the RHS of the ODE
            rhs: right-hand side for the linear system
            factor: abbrev. for the node-to-node stepsize (or any other factor required)
            u0: initial guess for the iterative solver (not used here so far)
            t: current time (e.g. for time-dependent BCs)

        Returns:
            solution as mesh
        """

        me = self.dtype_u(self.nvars)
        me.values = LA.spsolve(sp.eye(self.nvars) - factor * dfdu, rhs.values)
        return me