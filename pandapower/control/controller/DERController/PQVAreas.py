# -*- coding: utf-8 -*-

# Copyright (c) 2016-2024 by University of Kassel and Fraunhofer Institute for Energy Economics
# and Energy System Technology (IEE), Kassel. All rights reserved.

import numpy as np
try:
    from shapely.geometry import LineString, Point
    from shapely.geometry.polygon import Polygon
    shapely_imported = True
except ImportError:
    shapely_imported = False

from pandapower.auxiliary import soft_dependency_error
from pandapower.control.controller.DERController.DERBasics import BaseModel

try:
    import pandaplan.core.pplog as logging
except ImportError:
    import logging

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------------------------------
""" This file defines PQ, QV, and PQV areas of reactive power provision capabilities including those
defined in VDE-AR-N technical connection rule standards"""
# -------------------------------------------------------------------------------------------------

""" Base class """

class BaseArea(BaseModel):
    """ Defines which functionality is common to all area (PQ or QV) classes. """
    def in_area(self, p, q, vm_pu):
        min_max_q = self.q_flexibility(p, vm_pu)
        return (min_max_q[:, 0] <= q) & (min_max_q[:, 1] >= q)

    def q_flexibility(self, p, vm_pu):
        pass

    def __str__(self):
        return self.__class__.name


class BasePQVArea(BaseArea):
    """ Defines functionality common for mulitple PQVArea classes. """
    def in_area(self, p, q, vm_pu):
        return self.pq_area.in_area(p, q, vm_pu) & self.qv_area.in_area(p, q, vm_pu)

    def q_flexibility(self, p, vm_pu):
        min_max_q = self.pq_area.q_flexibility(p)
        min_max_q_qv = self.qv_area.q_flexibility(None, vm_pu)
        min_max_q[:, 0] = np.maximum(min_max_q[:, 0], min_max_q_qv[:, 0])
        min_max_q[:, 1] = np.minimum(min_max_q[:, 1], min_max_q_qv[:, 1])
        no_flexibility = min_max_q[:, 0] > min_max_q[:, 1]
        if n_no_flex := sum(no_flexibility):
            logger.debug(f"For {n_no_flex} elements, min_q and max_q were set to the same point of "
                         "no flexibility.")
            min_max_q[no_flexibility, :] = np.tile(np.sum(min_max_q[no_flexibility], axis=1)/2,
                                                   (1, 2))
        return min_max_q


""" Polygon Areas """

class PQAreaPOLYGON(BaseArea):
    """
    Provides a polygonal area of feasible reactive power provision. The polygonal area can be
    defined by 'p_points' and 'q_points'.

    Example
    -------
    >>> PQAreaDefault(p_points=(0.1, 0.2, 1, 1, 0.2, 0.1, 0.1),
    ...               q_points=(0.1, 0.410775, 0.410775, -0.328684, -0.328684, -0.1, 0.1))
    """
    def __init__(self, p_points, q_points):
        self.p_points = p_points
        self.q_points = q_points

        if not shapely_imported:
            soft_dependency_error("PQAreaDefault", "shapely")

        self.polygon = Polygon([(p, q) for p, q in zip(p_points, q_points)])

    def in_area(self, p, q, vm_pu=None):
        return np.array([self.polygon.contains(Point(pi, qi)) for pi, qi in zip(p, q)])

    def q_flexibility(self, p, vm_pu=None):
        def _q_flex(p):
            line = LineString([(p, -1), (p, 1)])
            if line.intersects(self.polygon):
                return [point[1] for point in LineString(
                    [(p, -1), (p, 1)]).intersection(self.polygon).coords]
            else:
                return [0, 0]
        return np.r_[[_q_flex(pi) for pi in p]]


class QVAreaPOLYGON(BaseArea):
    """
    Provides a polygonal area of feasible reactive power provision. The polygonal area can be
    defined by 'q_points' and 'vm_points'.

    Example
    -------
    >>> QVAreaPOLYGON(q_points=(0.1, 0.410775, 0.410775, -0.328684, -0.328684, -0.1, 0.1),
    ...               vm_points=(0.9, 1.05, 1.1, 1.1, 1.05, 0.9, 0.9))
    """
    def __init__(self, q_points, vm_points):
        self.q_points = q_points
        self.vm_points = vm_points

        if not shapely_imported:
            soft_dependency_error("PQAreaDefault", "shapely")

        # note that the naming QVAreaPOLYGON might be confusing because, in fact, it is a VQAreaPOLYGON
        self.polygon = Polygon([(vm, q) for vm, q in zip(vm_points, q_points)])

    def in_area(self, p, q, vm_pu):
        return np.array([self.polygon.contains(Point(vmi, qi)) for vmi, qi in zip(vm_pu, q)])

    def q_flexibility(self, p, vm_pu):
        assert all(vm_pu >= 0) and all(vm_pu <= 2)
        def _q_flex(vm):
            line = LineString([(vm, -1), (vm, 1)])
            if line.intersects(self.polygon):
                return [point[1] for point in LineString(
                    [(vm, -1), (vm, 1)]).intersection(self.polygon).coords]
            else:
                return [0, 0]
        return np.r_[[_q_flex(vmi) for vmi in vm_pu]]


class PQVAreaPOLYGON(BasePQVArea):
    """
    Provides a polygonal area of feasible reactive power provision. The polygonal area can be
    defined by 'p_points' and 'q_pq_points' as well as 'q_qv_points' and 'vm_points'.

    Example
    -------
    >>> PQVAreaDefault(p_points=(0.1, 0.2, 1, 1, 0.2, 0.1, 0.1),
    ...                q_pq_points=(0.1, 0.410775, 0.410775, -0.328684, -0.328684, -0.1, 0.1),
    ...                q_qv_points=(0.1, 0.410775, 0.410775, -0.328684, -0.328684, -0.1, 0.1),
    ...                vm_points=(0.9, 1.05, 1.1, 1.1, 1.05, 0.9, 0.9))
    """
    def __init__(self, p_points, q_pq_points, q_qv_points, vm_points):
        self.pq_area = PQAreaPOLYGON(p_points, q_pq_points)
        self.qv_area = QVAreaPOLYGON(q_qv_points, vm_points)


""" STATCOM DERs: """


class PQAreaSTATCOM(BaseArea):
    """
    TODO: Description

    Example
    -------
    >>> PQAreaSTATCOM(min_q=-0.328684, max_q=0.410775)
    """

    def __init__(self, min_q, max_q):
        self.min_q, self.max_q = min_q, max_q

    def in_area(self, p, q, vm_pu=None):
        return (self.min_q <= q) & (q <= self.max_q)

    def q_flexibility(self, p, vm_pu=None):
        return np.c_[[self.min_q]*len(p), [self.max_q]*len(p)]


""" HV DERs: """


class PQArea4120(BaseArea):
    """
    This class models the PQ area of flexible Q for high-voltage plants according to VDE AR-N-4120.
    It is used to be combined with Voltage dependencies in PQVArea4120V1, PQVArea4120V2 and
    PQVArea4120V3
    """
    def __init__(self, min_q, max_q, version=2018):
        supported_versions = [2015, 2018]
        p_points = {2015: [0.1, 0.2], 2018: [0.05, 0.2]}
        if version not in supported_versions:
            raise ValueError(
                f"version '{version}' is not supported, it is not in {supported_versions}")
        self.version = version
        self.p_points = p_points[version]
        self.min_q, self.max_q = min_q, max_q

        self.linear_factor_ind = (self.min_q + self.p_points[0]) / (self.p_points[1] - self.p_points[0])
        self.linear_factor_cap = (self.max_q - self.p_points[0]) / (self.p_points[1] - self.p_points[0])

    def in_area(self, p, q, vm_pu=None):
        is_in_area = np.ones(len(p), dtpye=bool)
        is_in_area[p < self.p_points[0]] = False
        if all(~is_in_area):
            return is_in_area
        is_in_area[(p > self.p_points[1]) & ((q < self.min_q) | (q > self.max_q))] = False
        if all(~is_in_area):
            return is_in_area
        is_in_area[(q < -self.p_points[0]-(p-self.p_points[0])*self.linear_factor_ind) | \
            (q > self.p_points[0]+(p-self.p_points[0])*self.linear_factor_cap)] = False
        return is_in_area

    def q_flexibility(self, p, vm_pu=None):
        q_flex = np.c_[[self.min_q]*len(p), [self.max_q]*len(p)]

        part = p < self.p_points[0]
        q_flex[part] = np.zeros((sum(part), 2))

        part = p < self.p_points[1]
        q_flex[part] = np.c_[-self.p_points[0]+(p[part]-self.p_points[0])*self.linear_factor_ind,
                             self.p_points[0]+(p[part]-self.p_points[0])*self.linear_factor_cap]


class QVArea4120(BaseArea):
    """
    This class models the QV area of flexible Q for high-voltage power plants according to
    VDE AR-N-4120.
    It is used to be combined with active power dependencies in PQVArea4120V1, PQVArea4120V2, or
    PQVArea4120V3
    """
    def __init__(self, min_q, max_q):
        self.min_q, self.max_q = min_q, max_q

        self.max_vm = 127.0/110
        self.min_vm = 96.0/110
        self.delta_vm = 7.0/110
        self.linear_factor = (self.max_q - self.min_q) / self.delta_vm

    def q_flexibility(self, p, vm_pu): # TODO
        if vm_pu < self.min_vm:
            q_range_qv_area = (self.max_q, self.max_q)
        elif self.min_vm < vm_pu <= self.min_vm + self.delta_vm:
            q_range_qv_area = (self.max_q - self.linear_factor * (vm_pu-self.min_vm), self.max_q)
        elif self.min_vm+self.delta_vm < vm_pu <= self.max_vm-self.delta_vm:
            q_range_qv_area = (self.min_q, self.max_q)
        elif self.max_vm-self.delta_vm < vm_pu <= self.max_vm:
            q_range_qv_area = (self.min_q, self.min_q + self.linear_factor * (self.max_vm-vm_pu))
        else:
            assert vm_pu > self.max_vm
            q_range_qv_area = (self.min_q, self.min_q)

        return q_range_qv_area


class PQVArea4120Base(BasePQVArea):
    """
    This is the base class for the three variants of VDE AR-N-4120. This class is not for direct
    application by the user.
    """
    def __init__(self, min_q, max_q, version=2018):
        self.pq_area = PQArea4120(min_q, max_q, version=version)
        self.qv_area = QVArea4120(min_q, max_q)

class PQVArea4120V1(PQVArea4120Base):
    """
    This class models the PQV area of flexible Q for high-voltage plants according to variant 1 of
    VDE AR-N-4120.
    """
    def __init__(self, version=2018):
        super().__init__(-0.227902, 0.484322, version=version)

class PQVArea4120V2(PQVArea4120Base):
    """
    This class models the PQV area of flexible Q for high-voltage plants according to variant 2 of
    VDE AR-N-4120.
    """
    def __init__(self, version=2018):
        super().__init__(-0.328684, 0.410775, version=version)


class PQVArea4120V3(PQVArea4120Base):
    """
    This class models the PQV area of flexible Q for high-voltage plants according to variant 3 of
    VDE AR-N-4120.
    """
    def __init__(self, version=2018):
        super().__init__(-0.410775, 0.328684, version=version)


""" EHV DERs: """

class PQArea4130(PQArea4120):
    pass  # equals PQArea4120 with possible exception for p<0.1 and q>0 (TODO)


class QVArea4130(QVArea4120):
    """
    This class models the QV area of flexible Q for extra high voltage power plants according to
    VDE AR-N-4130.
    It is used to be combined with active power dependencies in PQVArea4130V1, PQVArea4130V2, or
    PQVArea4130V3
    """
    def __init__(self, min_q, max_q, vn, variant):
        self.min_q, self.max_q, self.vn, self.variant = min_q, max_q, vn, variant
        epsilon = 1e-3
        if not np.any(np.isclose(np.array([380, 220]), vn)):
            raise ValueError(f"QVArea4130 is defined for 380kV and 220kV only, not for {vn}kV.")
        if variant == 1:
            if vn == 380:
                self.vm_min_points = np.array([350-epsilon, 350, 380, 400]) / vn
                self.vm_max_points = np.array([420, 440]) / vn
            elif vn == 220:
                self.vm_min_points = np.array([193-epsilon, 193, 220, 233.5]) / vn
                self.vm_max_points = np.array([245, 253]) / vn
            self.q_min_points = np.array([
                self.max_q, self.max_q*np.sin(np.arccos(0.95))/np.sin(np.arccos(0.9)), 0, self.min_q])
            self.q_max_points = np.array([self.max_q, self.min_q])
        elif variant == 2:
            if vn == 380:
                self.vm_min_points = np.array([350-epsilon, 350, 380, 410]) / vn
                self.vm_max_points = np.array([420, 440, 440+epsilon]) / vn
            elif vn == 220:
                self.vm_min_points = np.array([193-epsilon, 193, 220, 240]) / vn
                self.vm_max_points = np.array([245, 253, 253+epsilon]) / vn
            self.q_min_points = np.array([
                self.max_q, self.max_q*np.sin(np.arccos(0.95))/np.sin(np.arccos(0.925)), 0, self.min_q])
            self.q_max_points = np.array([self.max_q, 0, self.min_q])
        elif variant == 3:
            if vn == 380:
                self.vm_min_points = np.array([350, 380]) / vn
                self.vm_max_points = np.array([420, 440, 440+epsilon]) / vn
            elif vn == 220:
                self.vm_min_points = np.array([193, 220]) / vn
                self.vm_max_points = np.array([245, 253, 253+epsilon]) / vn
            self.q_min_points = np.array([self.max_q, self.min_q])
            self.q_max_points = np.array([self.max_q, 0, self.min_q])
        else:
            raise ValueError(
                f"QVArea4130 is defined for variants 1, 2, and 3 but not for {self.variant}.")

    def q_flexibility(self, p, vm_pu):
        return np.c_[np.interp(vm_pu, self.vm_min_points, self.q_min_points),
                     np.interp(vm_pu, self.vm_max_points, self.q_max_points)]


class PQVArea4130Base(BasePQVArea):
    """
    This is the base class for the three variants of VDE AR-N-4130. This class is not for direct
    application by the user.
    """
    def __init__(self, min_q, max_q, variant, version=2018, vn=380):
        self.pq_area = PQArea4130(min_q, max_q, version=version)
        self.qv_area = QVArea4130(min_q, max_q, vn=vn, variant=variant)


class PQVArea4130V1(PQVArea4130Base):
    """
    This class models the PQV area of flexible Q for extra high voltage power plants according to
    variant 1 of VDE AR-N-4130.
    """
    def __init__(self, version=2018, vn=380):
        super().__init__(-0.227902, 0.484322, 1, version=version, vn=vn)

class PQVArea4130V2(PQVArea4130Base):
    """
    This class models the PQV area of flexible Q for extra high voltage power plants according to
    variant 2 of VDE AR-N-4130.
    """
    def __init__(self, version=2018, vn=380):
        super().__init__(-0.328684, 0.410775, 2, version=version, vn=vn)


class PQVArea4130V3(PQVArea4130Base):
    """
    This class models the PQV area of flexible Q for extra high voltage power plants according to
    variant 3 of VDE AR-N-4130.
    """
    def __init__(self, version=2018, vn=380):
        super().__init__(-0.410775, 0.328684, 3, version=version, vn=vn)


""" MV DERs: """


class PQArea4110(PQAreaPOLYGON):
    def __init__(self):
        p_points = (0.0405, 0.81, 0.81, 0.0405, 0.0405)
        q_points = (-0.01961505, -0.3923009, 0.3923009, 0.01961505, -0.01961505)
        super().__init__(p_points, q_points)


class QVArea4110(BaseArea):
    """
    This class models the QV area of flexible Q for medium-voltage plants according to
    VDE AR-N-4110.
    """
    def __init__(self, min_q=-0.328684, max_q=0.328684):
        self.min_q, self.max_q = min_q, max_q
        self.min_vm, self.max_vm = 0.9, 1.1
        self.delta_vm = 0.025
        self.linear_factor_ind = (0 - self.min_q) / self.delta_vm
        self.linear_factor_cap = (self.max_q - 0) / self.delta_vm

    def q_flexibility(self, p, vm_pu):

        # part = vm_pu > self.max_vm
        len_ = len(vm_pu)
        min_max_q = np.c_[[self.min_q]*len_, [0]*len_]

        part = vm_pu < self.min_vm
        len_ = sum(part)
        min_max_q[part] = np.c_[[0]*len_, [self.max_q]*len_]

        part = (self.min_vm < vm_pu) & (vm_pu <= self.min_vm + self.delta_vm)
        min_max_q[part] = np.c_[-self.linear_factor_ind * (vm_pu[part]-self.min_vm),
                                [self.max_q]*sum(part)]

        part = (self.min_vm+self.delta_vm < vm_pu) & (vm_pu <= self.max_vm-self.delta_vm)
        min_max_q[part] = np.repeat(np.array([[self.min_q, self.max_q]]), sum(part), axis=0)

        part = (self.max_vm-self.delta_vm < vm_pu) & (vm_pu <= self.max_vm)
        min_max_q[part] = np.c_[[self.min_q]*sum(part),
                                self.linear_factor_cap * (-vm_pu[part]+self.max_vm)]

        return min_max_q

class PQVArea4110(BasePQVArea):
    def __init__(self, min_q=-0.328684, max_q=0.328684):
        # alternative to [-0.328684, 0.328684] is [-0.484322, 0.484322] with allowed p reduction
        # outside [-0.328684, 0.328684]
        self.pq_area = PQArea4110()
        self.qv_area = QVArea4110(min_q, max_q)

""" LV DERs: """


class PQArea4105(BaseArea):
    """
    This class models the PQ area of flexible Q for low-voltage plants according to VDE AR-N-4105.
    """
    def __init__(self, min_q=-0.328684, max_q=0.328684):
        self.min_q, self.max_q = min_q, max_q
        self.linear_factor_ind = self.min_q / 0.9
        self.linear_factor_cap = self.max_q / 0.9

    def in_area(self, p, q, vm_pu=None): # TODO
        if p < 0.1:
            return False
        elif q < (p-0.1)*self.linear_factor_ind or q > (p-0.1)*self.linear_factor_cap:
            return False
        else:
            return True

    def q_flexibility(self, p, vm_pu=None): # TODO
        if p < 0.1:
            return (0, 0)
        else:
            return ((p-0.1)*self.linear_factor_ind, (p-0.1)*self.linear_factor_cap)


class QVArea4105(BaseArea):
    """
    This class models the QV area of flexible Q for low-voltage plants according to VDE AR-N-4105.
    """
    def __init__(self, min_cosphi, max_cosphi):
        self.min_cosphi, self.max_cosphi = min_cosphi, max_cosphi
        self.min_vm, self.max_vm = 0.9, 1.1
        self.delta_vm = 0.05
        self.linear_factor_ind = (1 - self.min_cosphi) / self.delta_vm
        self.linear_factor_cap = (1 - self.max_cosphi) / self.delta_vm

    def q_flexibility(self, p, vm_pu): # TODO
        if vm_pu < self.min_vm:
            cosphi_range_qv_area = (1, self.max_cosphi)
        elif self.min_vm < vm_pu <= self.min_vm + self.delta_vm:
            cosphi_range_qv_area = (1 - self.linear_factor_ind * (vm_pu-self.min_vm),
                                    self.max_cosphi)
        elif self.min_vm+self.delta_vm < vm_pu <= self.max_vm-self.delta_vm:
            cosphi_range_qv_area = (self.min_cosphi, self.max_cosphi)
        elif self.max_vm-self.delta_vm < vm_pu <= self.max_vm:
            cosphi_range_qv_area = (self.min_cosphi,
                                    1 - self.linear_factor_cap * (self.max_vm-vm_pu))
        else:
            assert vm_pu > self.max_vm
            cosphi_range_qv_area = (self.min_cosphi, 1)

        q_range_qv_area = (-1 * np.tan(np.arccos(cosphi_range_qv_area[0])),
                           1 * np.tan(np.arccos(cosphi_range_qv_area[1])))
        return q_range_qv_area

class PQVArea4105(BasePQVArea):
    """
    This class models the PQV area of flexible Q for low-voltage plants according to VDE AR-N-4105.
    """
    def __init__(self, min_cosphi, max_cosphi, min_q=-0.328684, max_q=0.328684):
        self.pq_area = PQArea4105(min_q=min_q, max_q=max_q)
        self.qv_area = QVArea4105(min_cosphi, max_cosphi)


if __name__ == "__main__":
    pass
