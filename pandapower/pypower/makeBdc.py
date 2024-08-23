# -*- coding: utf-8 -*-

# Copyright 1996-2015 PSERC. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

# Copyright (c) 2016-2024 by University of Kassel and Fraunhofer Institute for Energy Economics
# and Energy System Technology (IEE), Kassel. All rights reserved.


"""Builds the B matrices and phase shift injections for DC power flow.
"""
from numpy import ones, zeros_like, r_, pi, flatnonzero as find, real, int64, float64, divide, errstate
from pandapower.pypower.idx_brch import F_BUS, T_BUS, BR_X, TAP, SHIFT, BR_STATUS
from pandapower.pypower.idx_bus import BUS_I

from scipy.sparse import csr_matrix, csc_matrix

try:
    import pandaplan.core.pplog as logging
except ImportError:
    import logging

logger = logging.getLogger(__name__)


def makeBdc(bus, branch, return_csr=True):
    """Builds the B matrices and phase shift injections for DC power flow.

    Returns the B matrices and phase shift injection vectors needed for a
    DC power flow.
    The bus real power injections are related to bus voltage angles by::
        P = Bbus * Va + PBusinj
    The real power flows at the from end the lines are related to the bus
    voltage angles by::
        Pf = Bf * Va + Pfinj
    Does appropriate conversions to p.u.

    @see: L{dcpf}

    @author: Carlos E. Murillo-Sanchez (PSERC Cornell & Universidad
    Autonoma de Manizales)
    @author: Ray Zimmerman (PSERC Cornell)
    @author: Richard Lincoln
    """
    ## Select csc/csr B matrix
    sparse = csr_matrix if return_csr else csc_matrix

    ## constants
    nb = bus.shape[0]          ## number of buses
    nl = branch.shape[0]       ## number of lines

    ## check that bus numbers are equal to indices to bus (one set of bus nums)
    if any(bus[:, BUS_I] != list(range(nb))):
        logger.error('makeBdc: buses must be numbered consecutively in '
                     'bus matrix\n')

    ## for each branch, compute the elements of the branch B matrix and the phase
    ## shift "quiescent" injections, where
    ##
    ##      | Pf |   | Bff  Bft |   | Vaf |   | Pfinj |
    ##      |    | = |          | * |     | + |       |
    ##      | Pt |   | Btf  Btt |   | Vat |   | Ptinj |
    ##
    b = calc_b_from_branch(branch, nl)

    ## build connection matrix Cft = Cf - Ct for line and from - to buses
    f = real(branch[:, F_BUS]).astype(int64)                           ## list of "from" buses
    t = real(branch[:, T_BUS]).astype(int64)                           ## list of "to" buses
    i = r_[range(nl), range(nl)]                   ## double set of row indices
    ## connection matrix
    Cft = sparse((r_[ones(nl), -ones(nl)], (i, r_[f, t])), (nl, nb))

    ## build Bf such that Bf * Va is the vector of real branch powers injected
    ## at each branch's "from" bus
    Bf = sparse((r_[b, -b], (i, r_[f, t])), (nl, nb))## = spdiags(b, 0, nl, nl) * Cft

    ## build Bbus
    Bbus = Cft.T * Bf

    ## build phase shift injection vectors
    Pfinj, Pbusinj = phase_shift_injection(b, branch[:, SHIFT], Cft)

    return Bbus, Bf, Pbusinj, Pfinj, Cft


def phase_shift_injection(b, shift, Cft):
    ## build phase shift injection vectors
    Pfinj = b * (-shift * pi / 180.)  ## injected at the from bus ...
    # Ptinj = -Pfinj                            ## and extracted at the to bus
    Pbusinj = Cft.T * Pfinj  ## Pbusinj = Cf * Pfinj + Ct * Ptinj
    return Pfinj, Pbusinj


# we set the numpy error handling for this function to raise error rather than issue a warning because
# otherwise the resulting nan values will propagate and case an error elsewhere, making the reason less obvious
@errstate(all="raise")
def calc_b_from_branch(branch, nl):
    stat = real(branch[:, BR_STATUS])  ## ones at in-service branches
    br_x = real(branch[:, BR_X])  ## ones at in-service branches
    b = zeros_like(stat, dtype=float64)
    # if some br_x values are 0 but the branches are not in service, we do not need to raise an error:
    # divide(x1=stat, x2=br_x, out=b, where=stat, dtype=float64)  ## series susceptance
    # however, we also work with ppci at this level, which only has in-service elements so we should just let it fail:
    divide(stat, br_x, out=b, dtype=float64)  ## series susceptance
    tap = ones(nl)  ## default tap ratio = 1
    i = find(t := real(branch[:, TAP]))  ## indices of non-zero tap ratios
    tap[i] = t[i]  ## assign non-zero tap ratios
    b = b / tap
    return b
