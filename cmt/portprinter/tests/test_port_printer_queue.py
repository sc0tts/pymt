#! /usr/bin/env python

import cmt.printqueue.port_printer_queue as ppq
from cmt.testing.ports import UniformRectilinearGridPort
from cmt.testing.assertions import assert_isfile_and_remove


def test_uniform_rectilinear_vtk():
    port = UniformRectilinearGridPort()

    queue = ppq.PortPrinterQueue(port)
    queue.append('air__density', format='vtk')
    queue.open()
    for _ in xrange(5):
        queue.write()
    queue.close()

    assert_isfile_and_remove('air__density_0000.vtu')
    assert_isfile_and_remove('air__density_0001.vtu')
    assert_isfile_and_remove('air__density_0002.vtu')
    assert_isfile_and_remove('air__density_0003.vtu')
    assert_isfile_and_remove('air__density_0004.vtu')


def test_uniform_rectilinear_nc():
    port = UniformRectilinearGridPort()

    queue = ppq.PortPrinterQueue(port)
    queue.append('glacier_top_surface__slope', format='nc')
    queue.open()
    for _ in xrange(5):
        queue.write()
    queue.close()

    assert_isfile_and_remove('glacier_top_surface__slope.nc')


def test_from_string():
    port = UniformRectilinearGridPort()
    ini_string = """
[print.air__density]
format=vtk

[print.glacier_top_surface__slope]
format=nc
    """
    queue = ppq.PortPrinterQueue.from_string(ini_string, port)
    queue.open()
    queue.write()
    queue.close()

    assert_isfile_and_remove('glacier_top_surface__slope.nc')
    assert_isfile_and_remove('air__density_0000.vtu')