"""Bridge between BMI and a PyMT component."""
from __future__ import print_function

import ctypes
import json
import os
from pprint import pformat

import numpy as np
import yaml
from cfunits import Units
from deprecated import deprecated
from scripting.contexts import cd

from ..errors import BmiError
from .bmi_docstring import bmi_docstring
from .bmi_mapper import GridMapperMixIn
from .bmi_plot import quick_plot
from .bmi_setup import SetupMixIn
from .bmi_timeinterp import BmiTimeInterpolator
from .bmi_ugrid import dataset_from_bmi_grid


def transform_math_to_azimuth(angle, units):
    angle *= -1.0
    if units == Units("rad"):
        angle += np.pi * 0.5
    else:
        angle += 90.0


def transform_azimuth_to_math(angle, units):
    angle *= -1.0
    if units == Units("rad"):
        angle -= np.pi * 0.5
    else:
        angle -= 90.0


class DataValues(object):
    def __init__(self, bmi, name):
        self._bmi = bmi
        self._name = name

    @property
    def name(self):
        return self._name

    @property
    def units(self):
        return self._bmi.get_var_units(self.name)

    @property
    def grid(self):
        return self._bmi.get_var_grid(self.name)

    @property
    def size(self):
        return self._bmi.get_var_size(self.name)

    @property
    def type(self):
        return self._bmi.get_var_type(self.name)

    @property
    def intent(self):
        return self._bmi.get_var_intent(self.name)

    @property
    def location(self):
        return self._bmi.get_var_grid_loc(self.name)

    @property
    def data(self):
        return self.values()

    def values(self, **kwds):
        if "out" in self.intent:
            return self._bmi.get_value(self.name, **kwds)
        else:
            raise ValueError("not an output var")

    def __repr__(self):
        return str(self)

    def __str__(self):
        return """
<DataValues>
{dtype} {name}({location})
Attributes:
    units: {units}
    grid: {grid}
    intent: {intent}
    location: {location}
""".format(
            dtype=self.type,
            name=self.name,
            units=self.units,
            grid=self.grid,
            intent=self.intent,
            location=self.location,
        ).strip()


class _BmiCapV1(object):

    """Add methods for backward compatibility."""

    @staticmethod
    def _call_bmi(func, *args):
        rtn = func(*args)

        try:
            status, val = rtn
        except TypeError:
            status, val = rtn, None

        if status != 0:
            raise BmiError(func.__name__ + pformat(args), status)
        else:
            return val

    @deprecated(reason="use get_grid_number_of_vertices")
    def get_grid_vertex_count(self, grid):
        return _BmiCapV1._call_bmi(self.bmi.get_grid_vertex_count, grid)

    @deprecated(reason="use get_grid_number_of_faces")
    def get_grid_face_count(self, grid):
        return _BmiCapV1._call_bmi(self.bmi.get_grid_face_count, grid)

    @deprecated(reason="use get_grid_face_node_connectivity")
    def get_grid_connectivity(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_vertex_count(grid), dtype=ctypes.c_int)
        return _BmiCapV1._call_bmi(self.bmi.get_grid_connectivity, grid, out)

    @deprecated(reason="use get_grid_face_node_offset")
    def get_grid_offset(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_face_count(grid), dtype=ctypes.c_int)
        return _BmiCapV1._call_bmi(self.bmi.get_grid_offset, grid, out)


class _BmiCapV2(object):
    @deprecated(reason="use get_grid_number_of_vertices")
    def get_grid_vertex_count(self, grid):
        return self.get_grid_number_of_vertices(grid)

    @deprecated(reason="use get_grid_number_of_faces")
    def get_grid_face_count(self, grid):
        return self.get_grid_number_of_faces(grid)

    @deprecated(reason="use get_grid_face_node_connectivity")
    def get_grid_connectivity(self, grid, out=None):
        return self.get_grid_face_node_connectivity(grid, out=out)

    @deprecated(reason="use get_grid_face_node_offset")
    def get_grid_offset(self, grid, out=None):
        return self.get_grid_face_node_offset(grid, out=out)


class _BmiCap(object):
    def __init__(self):
        self._bmi = self._cls()
        self._initialized = False
        self._grid = dict()
        self._var = dict()
        self._time_units = None
        self._initdir = None
        super(_BmiCap, self).__init__()

    @property
    def bmi(self):
        return self._bmi

    @property
    def name(self):
        return self.get_component_name()

    @property
    def grid(self):
        return self._grid

    @property
    def var(self):
        return self._var

    @property
    def initdir(self):
        return self._initdir

    def _grid_ids(self):
        grids = set()
        for var in set(self.input_var_names + self.output_var_names):
            grids.add(self.get_var_grid(var))
        return tuple(grids)

    def get_component_name(self):
        return self.bmi.get_component_name()

    def initialize(self, fname=None, dir="."):  # pylint: disable=redefined-builtin
        """Initialize the model.

        Parameters
        ----------
        fname : str
            Name of initialization file.
        dir : str
            Path to folder in which to run initialization.
        """
        self._initdir = os.path.abspath(dir)
        with cd(self.initdir, create=False):
            self.bmi.initialize(fname or "")
            self._initialized = True

        for grid_id in self._grid_ids():
            self._grid[grid_id] = dataset_from_bmi_grid(self, grid_id)

        for name in set(self.output_var_names + self.input_var_names):
            self._var[name] = DataValues(self, name)

    def update(self):
        with cd(self.initdir):
            return self.bmi.update()

    def finalize(self):
        with cd(self.initdir):
            self._initialized = False
            return self.bmi.finalize()

    def set_value(self, name, val):
        val = np.asarray(val).reshape((-1,))
        return self.bmi.set_value(name, val)

    def get_value(self, name, out=None, units=None, angle=None, at=None, method=None):
        if out is None:
            grid = self.get_var_grid(name)
            dtype = self.get_var_type(name)
            if dtype == "":
                raise ValueError("{name} not understood".format(name=name))
            loc = self.get_var_grid_loc(name)
            out = np.empty(self.get_grid_dim(grid, loc), dtype=dtype)

        self.bmi.get_value(name, out)

        if name in self._interpolators and at is not None:
            out[:] = self._interpolators[name].interpolate(at)

        from_units = Units(self.get_var_units(name))
        if units is not None:
            to_units = Units(units)
        else:
            to_units = from_units

        if units is not None and from_units != to_units:
            Units.conform(out, from_units, to_units, inplace=True)

        # if units is not None:
        #     try:
        #         from_units = self.get_var_units(name)
        #     except AttributeError, NotImplementedError:
        #         pass
        #     else:
        #         Units.conform(out, Units(from_units), Units(units),
        #                       inplace=True)

        if angle not in ("azimuth", "math", None):
            raise ValueError("angle not understood")

        if angle == "azimuth" and "azimuth" not in name:
            transform_math_to_azimuth(out, to_units)
        elif angle == "math" and "azimuth" in name:
            transform_azimuth_to_math(out, to_units)

        return out

    def get_value_ptr(self, name):
        return self.bmi.get_value_ptr(name)

    @deprecated(reason="use get_grid_ndim")
    def get_grid_rank(self, grid):
        return self.get_grid_ndim(grid)

    def get_grid_ndim(self, grid):
        return self.bmi.get_grid_rank(grid)

    NUMBER_OF_ELEMENTS = {
        "node": "get_grid_number_of_nodes",
        "edge": "get_grid_number_of_edges",
        "face": "get_grid_number_of_faces",
        "vertex": "get_grid_number_of_vertices",
    }

    def get_grid_dim(self, grid, dim):
        return getattr(self, self.NUMBER_OF_ELEMENTS[dim])(grid)

    @deprecated(reason="use get_grid_number_of_nodes")
    def get_grid_size(self, grid):
        return self.get_grid_number_of_nodes(grid)

    def get_grid_type(self, grid):
        return self.bmi.get_grid_type(grid)

    def get_grid_shape(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_ndim(grid), dtype=ctypes.c_int)
        self.bmi.get_grid_shape(grid, out)
        return out

    def get_grid_spacing(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_ndim(grid), dtype=ctypes.c_double)
        self.bmi.get_grid_spacing(grid, out)
        return out

    def get_grid_origin(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_ndim(grid), dtype=ctypes.c_double)
        self.bmi.get_grid_origin(grid, out)
        return out

    def get_grid_number_of_nodes(self, grid):
        return self.bmi.get_grid_size(grid)

    def get_grid_number_of_vertices(self, grid):
        return self.get_grid_nodes_per_face(grid).sum()

    def get_grid_number_of_faces(self, grid):
        return self.bmi.get_grid_number_of_faces(grid)

    def get_grid_face_node_connectivity(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_number_of_vertices(grid), dtype=ctypes.c_int)
        self.bmi.get_grid_face_nodes(grid, out)
        return out

    def get_grid_face_nodes(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_number_of_vertices(grid), dtype=ctypes.c_int)
        self.bmi.get_grid_face_nodes(grid, out)
        return out

    def get_grid_face_node_offset(self, grid, out=None):
        nodes_per_face = self.get_grid_nodes_per_face(grid, out=out)
        return np.cumsum(nodes_per_face, out=out)

    def get_grid_nodes_per_face(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_number_of_faces(grid), dtype=ctypes.c_int)
        self.bmi.get_grid_nodes_per_face(grid, out)
        return out

    def get_grid_x(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_number_of_nodes(grid), dtype=float)
        self.bmi.get_grid_x(grid, out)
        return out

    def get_grid_y(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_number_of_nodes(grid), dtype=float)
        self.bmi.get_grid_y(grid, out)
        return out

    def get_grid_z(self, grid, out=None):
        if out is None:
            out = np.empty(self.get_grid_number_of_nodes(grid), dtype=float)
        self.bmi.get_grid_z(grid, out)
        return out

    @property
    def input_var_names(self):
        return tuple(self.bmi.get_input_var_names())

    def get_input_var_names(self):
        return self.input_var_names

    @property
    def output_var_names(self):
        return tuple(self.bmi.get_output_var_names())

    def get_output_var_names(self):
        return self.output_var_names

    @property
    def time_units(self):
        return self._time_units or self.get_time_units()
        # return self.get_time_units()

    @time_units.setter
    def time_units(self, new_units):
        self._time_units = new_units

    def get_time_units(self):
        return self.bmi.get_time_units()

    def get_current_time(self, units=None):
        time = self.bmi.get_current_time()

        return self.time_in(time, units)

    def get_start_time(self, units=None):
        time = self.bmi.get_start_time()

        return self.time_in(time, units)

    def get_end_time(self, units=None):
        time = self.bmi.get_end_time()

        return self.time_in(time, units)

    def get_time_step(self, units=None):
        time = self.bmi.get_time_step()

        return self.time_in(time, units)

    def time_in(self, time, units):
        if units is None:
            units = self.time_units
            # return time

        try:
            units_str = self.get_time_units()
            # units_str = self.time_units
        except (AttributeError, NotImplementedError):
            pass
        else:
            from_units = Units(units_str)
            to_units = Units(units)

            if not from_units.equals(to_units):
                time = Units.conform(time, from_units, to_units)

        return time

    def time_from(self, time, units):
        if units is None:
            return time

        try:
            # units_str = self.get_time_units()
            units_str = self.time_units
        except (AttributeError, NotImplementedError):
            pass
        else:
            to_units = Units(units_str)
            from_units = Units(units)

            if not from_units.equals(to_units):
                time = Units.conform(time, from_units, to_units)

        return time

    def get_var_intent(self, name):
        intent = ""
        if name in self.input_var_names:
            intent += "in"
        if name in self.output_var_names:
            intent += "out"
        return intent

    def get_var_location(self, name):
        return self.get_var_grid_loc(name)

    def get_var_grid_loc(self, name):
        try:
            self.bmi.get_var_location
        except AttributeError:
            return "node"
        else:
            return self.bmi.get_var_location(name)

    def get_var_grid(self, name):
        return self.bmi.get_var_grid(name)

    def get_var_itemsize(self, name):
        return self.bmi.get_var_itemsize(name)

    def get_var_nbytes(self, name):
        return self.bmi.get_var_nbytes(name)

    def get_var_type(self, name):
        return self.bmi.get_var_type(name)

    def get_var_units(self, name):
        units = self.bmi.get_var_units(name)
        if units == "-":
            return ""
        else:
            return units

    def as_dict(self):
        vars_ = {}
        grid_ids = set()
        for var in set(self.input_var_names + self.output_var_names):
            var_desc = {
                # 'name': var,
                "intent": "",
                "units": self.get_var_units(var),
                "dtype": self.get_var_type(var),
                "itemsize": self.get_var_itemsize(var),
                "nbytes": self.get_var_nbytes(var),
                "grid": self.get_var_grid(var),
            }
            vars_[var] = var_desc

            if var in self.input_var_names:
                var_desc["intent"] += "in"
            if var in self.output_var_names:
                var_desc["intent"] += "out"
            # vars_.append(var_desc)
            grid_ids.add(var_desc["grid"])
        # vars_.sort(cmp=lambda a, b: cmp(a['name'], b['name']))

        grids = {}
        for grid_id in grid_ids:
            grid_desc = {
                # 'id': grid_id,
                "rank": self.get_grid_ndim(grid_id),
                "size": self.get_grid_number_of_nodes(grid_id),
                "type": self.get_grid_type(grid_id),
            }
            grids[grid_id] = grid_desc
            # grids.append(grid_desc)
        # grids.sort(cmp=lambda a, b: cmp(a['id'], b['id']))

        in_vars = list(self.input_var_names)
        out_vars = list(self.output_var_names)
        in_vars.sort()
        out_vars.sort()

        times = {
            "start": self.get_start_time(),
            "end": self.get_end_time(),
            "current": self.get_current_time(),
            # 'time_step': self.get_time_step(),
            "units": self.get_time_units(),
        }
        return {
            "name": self.name,
            "input_var_names": in_vars,
            "output_var_names": out_vars,
            "vars": vars_,
            "grids": grids,
            "times": times,
        }

    def as_yaml(self):
        return yaml.dump(self.as_dict(), default_flow_style=False)

    def as_json(self):
        return json.dumps(self.as_dict())

    def quick_plot(self, name, **kwds):
        return quick_plot(self, name, **kwds)

    def __str__(self):
        return yaml.dump(
            {
                "name": self.name,
                "input_var_names": list(self.input_var_names),
                "output_var_names": list(self.output_var_names),
            },
            default_flow_style=False,
        )


class BmiCap(GridMapperMixIn, _BmiCap, BmiTimeInterpolator, SetupMixIn):
    pass


def bmi_factory(cls):
    class BmiWrapper(BmiCap):
        # __doc__ = bmi_docstring(cls.__name__.split('.')[-1])
        __doc__ = bmi_docstring(cls)
        _cls = cls

        def __str__(self):
            return "{0}".format(cls.__name__)

        def __repr__(self):
            return "<{0}()>".format(cls.__name__)

    BmiWrapper.__name__ = cls.__name__
    return BmiWrapper
