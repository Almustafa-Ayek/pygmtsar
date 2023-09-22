# ----------------------------------------------------------------------------
# PyGMTSAR
# 
# This file is part of the PyGMTSAR project: https://github.com/mobigroup/gmtsar
# 
# Copyright (c) 2023, Alexey Pechnikov
# 
# Licensed under the BSD 3-Clause License (see LICENSE for details)
# ----------------------------------------------------------------------------
from .Stack_trans_inv import Stack_trans_inv
from .PRM import PRM
from .tqdm_dask import tqdm_dask

class Stack_topo(Stack_trans_inv):

    def topo(self, chunksize=None, interactive=False):
        """
        Compute the topography in radar coordinates (topo).

        Parameters
        ----------
        interactive : bool, optional
            If True, the computation will be performed interactively and the result will be returned as a delayed object.
            Default is False.
        """
        import dask
        import xarray as xr
        import numpy as np
        #import os

        # GMTSAR phasediff tool requires "The dimension SLC must be multiplication factor of the topo"
        topo = self.get_trans_inv().ele[1:,1:].rename('topo')
        # add average topography for topo phase removal in phasediff
        topo['average'] = topo.mean()
    
        if interactive:
            # do not flip vertically because it's returned as is without Stack.get_topo() function
            return topo
        # flip vertically for GMTSAR compatibility reasons
        topo = xr.DataArray(dask.array.flipud(topo), coords=topo.coords, name=topo.name)
        # rename to save lazy NetCDF preventing broken coordinates (y,y)
        return self.save_grid(topo.rename({'y': 'a', 'x': 'r'}),
                              'topo', f'Radar Topography Computing', chunksize)

    def get_topo(self, chunksize=None):
        """
        Get the radar topography grid.

        Returns
        -------
        xarray.DataArray or list of xarray.DataArray
            The 'topo' grid data as a single xarray.DataArray if only one grid is found,
            or a list of xarray.DataArray if multiple grids are found.

        Examples
        --------
        Get DEM:
        topo = stack.get_topo()

        Notes
        -----
        This method opens the 'topo' grids using the `open_grids` method and applies the `func` function
        to each grid to flip it vertically for compatibility reasons with GMTSAR. The resulting grids are returned.
        """
        import xarray as xr
        import dask.array

        if chunksize is None:
            chunksize = self.chunksize

        def func(topo):
            # flip vertically for GMTSAR compatibility reasons
            return xr.DataArray(dask.array.flipud(topo), coords=topo.coords, attrs=topo.attrs, name=topo.name)

        topos = self.open_grid('topo', chunksize=chunksize)
        return func(topos)
