# ----------------------------------------------------------------------------
# PyGMTSAR
# 
# This file is part of the PyGMTSAR project: https://github.com/mobigroup/gmtsar
# 
# Copyright (c) 2021, Alexey Pechnikov
# 
# Licensed under the BSD 3-Clause License (see LICENSE for details)
# ----------------------------------------------------------------------------
from .SBAS_sbas import SBAS_sbas
from .tqdm_dask import tqdm_dask

class SBAS_geocode(SBAS_sbas):

    def geocode_parallel(self, pairs=None, chunksize=None):
        """
        Perform parallel geocoding of the interferograms.

        Parameters
        ----------
        pairs : list or None, optional
            List of interferogram pairs to process. If None, all available pairs will be processed.

        Notes
        -----
        This method performs parallel geocoding of the interferograms. It builds the necessary geocoding matrices
        to apply the geocoding transformation to the interferogram grids. The geocoding involves converting the
        radar coordinates to geographic coordinates and vice versa.
        """

        # build trans_dat, trans_ dat_inv and topo_ra grids for merged subswaths
        # for single-digit subswath the grids already created for interferogram processing
        if len(str(self.get_subswath())) > 1:
            self.topo_ra_parallel()

        # build geographic coordinates transformation matrix for landmask and other grids
        self.intf_ll2ra_matrix_parallel(pairs=pairs, chunksize=chunksize)
        # build radar coordinates transformation matrix for the interferograms grid stack        
        self.intf_ra2ll_matrix_parallel(pairs=pairs, chunksize=chunksize)

##########################################################################################
# ra2ll
##########################################################################################
    def intf_ra2ll_matrix_parallel(self, pairs=None, chunksize=None, interactive=False):
        """
        Perform parallel computation of the radar-to-geographic coordinate transformation matrix.

        Parameters
        ----------
        pairs : list or None, optional
            List of interferogram pairs to process. If None, all available pairs will be processed.
        interactive : bool, optional
            Flag indicating whether to return the matrix without saving to a file.
        """
        import xarray as xr
        import numpy as np
        import dask
        import os

        if chunksize is None:
            chunksize = self.chunksize

        pairs = self.pairs(pairs)

        # find any one interferogram to define the grid
        intf = self.open_grids(pairs[:1], 'phasefilt')[0].astype(bool)
        dy = np.diff(intf.y)[0]
        dx = np.diff(intf.x)[0]

        # get transform table
        trans = self.get_trans_dat()
        trans_dy = np.diff(trans.y)[0]
        trans_dx = np.diff(trans.x)[0]

        # define transform spacing in radar coordinates
        step_y = int(np.round(dy / trans_dy))
        step_x = int(np.round(dx / trans_dx))
        #print ('step_y', step_y, 'step_x', step_x)

        # define the equally spacing geographic coordinates grid
        lats = trans.lat[::step_y]
        lons = trans.lon[::step_x]

        # decimate the full trans grid to the required spacing
        trans = trans.sel(lat=lats, lon=lons)[['azi', 'rng']]
        # define interferogram radar coordinates grid
        trans['y'] = xr.DataArray(intf.y.values, dims='y')
        trans['x'] = xr.DataArray(intf.x.values, dims='x')

        if interactive:
            return trans

        # save to NetCDF file
        filename = self.get_filenames(None, None, 'intf_ra2ll')
        #print ('filename', filename)
        # to resolve NetCDF rewriting error
        if os.path.exists(filename):
            os.remove(filename)
        encoding = {var: self.compression(trans[var].shape, chunksize=chunksize) for var in trans.data_vars}
        handler = trans.to_netcdf(filename,
                                  encoding=encoding,
                                  engine=self.engine,
                                  compute=False)
        tqdm_dask(dask.persist(handler), desc='Build ra2ll Transform')
        handler.close()

    def get_intf_ra2ll(self, subswath=None, chunksize=None):
        """
        Get the radar-to-geographic coordinate transformation matrix.

        Parameters
        ----------
        chunksize : int or dict, optional
            Chunk size for dask arrays. If not provided, the default chunk size is used.

        Returns
        -------
        xarray.DataArray
            The radar-to-geographic coordinate transformation matrix.

        Notes
        -----
        This method retrieves the radar-to-geographic coordinate transformation matrix (intf_ra2ll) stored in the
        NetCDF grid. The matrix is useful for inverse geocoding, converting interferogram grids from radar
        coordinates to geographic coordinates.
        """
        import xarray as xr

        subswath = self.get_subswath(subswath)
        filename = self.get_filenames(subswath, None, 'intf_ra2ll')
        trans = xr.open_dataset(filename, engine=self.engine, chunks=self.chunksize)
        return trans

    def intf_ra2ll(self, grids, chunksize=None):
        """
        Perform geocoding from radar to geographic coordinates.

        Parameters
        ----------
        grids : xarray.DataArray
            Grid(s) representing the interferogram(s) in radar coordinates.
        chunksize : int or dict, optional
            Chunk size for dask arrays. If not provided, the default chunk size is used.

        Returns
        -------
        xarray.DataArray
            The inverse geocoded grid(s) in geographic coordinates.

        Examples
        --------
        Geocode 3D unwrapped phase grids stack:
        unwraps_ll = sbas.intf_ra2ll(sbas.open_grids(pairs, 'unwrap'))
        # or use "geocode" option for open_grids() instead:
        unwraps_ll = sbas.open_grids(pairs, 'unwrap', geocode=True)
        """
        import dask
        import xarray as xr
        import numpy as np

        # helper check
        if not 'y' in grids.dims or not 'x' in grids.dims:
            print ('NOTE: the input grid is not in radar coordinates, miss geocoding')
            return grids

        if chunksize is None:
            chunksize = self.chunksize

        @dask.delayed
        def intf_block(trans, grid_ra):
            from scipy.interpolate import RegularGridInterpolator

            # use trans table subset
            y = trans.azi.values.ravel()
            x = trans.rng.values.ravel()
            points = np.column_stack([y, x])

            # get interferogram full grid
            ys = grid_ra.y.values
            xs = grid_ra.x.values

            # calculate trans grid subset extent
            ymin, ymax = np.nanmin(y), np.nanmax(y)
            xmin, xmax = np.nanmin(x), np.nanmax(x)
            # and spacing
            dy = np.diff(ys)[0]
            dx = np.diff(xs)[0]

            # select required interferogram grid subset
            ys = ys[(ys>ymin-dy)&(ys<ymax+dy)]
            xs = xs[(xs>xmin-dx)&(xs<xmax+dx)]
        
            # for cropped interferogram we can have no valid pixels for the processing
            if ys.size == 0 or xs.size == 0:
                return np.nan * np.zeros((trans.lat.size, trans.lon.size), dtype=np.float32)
        
            values = grid_ra.sel(y=ys, x=xs).values.astype(np.float64)

            # perform interpolation
            interp = RegularGridInterpolator((ys, xs), values, method='nearest', bounds_error=False)
            grid_ll = interp(points).reshape(trans.lat.size, trans.lon.size).astype(np.float32)

            return grid_ll

        # get transform table
        trans = self.get_intf_ra2ll()[['azi', 'rng']]
        lats = trans.lat
        lons = trans.lon
        # define processing blocks
        chunks = lats.size / chunksize
        lons_blocks = np.array_split(lons, np.arange(0, lons.size, chunksize)[1:])

        grids_ll = []
        # unify input grid(s) to stack
        for grid_ra in grids if len(grids.dims) == 3 else [grids]:
            # per-block processing
            blocks  = []
            for lons_block in lons_blocks:
                block = dask.array.from_delayed(intf_block(trans.sel(lon=lons_block), grid_ra),
                                                shape=(lats.size, lons_block.size), dtype=np.float32)
                blocks.append(block)
            #grid_ll = dask.array.block(blocks)
            # set the output grid and drop the fake dimension if needed
            grid_ll = xr.DataArray(dask.array.block(blocks), coords=trans.coords).rename(grids.name)
            grids_ll.append(grid_ll)

        if len(grids.dims) == 2:
            # drop the fake dimension
            coords = trans.coords
            out = xr.DataArray(grids_ll[0], coords=coords).rename(grids.name)
        else:
            # find stack dim
            stack_dim = grids.dims[0]
            coords = {stack_dim: grids[stack_dim], 'lat': trans.lat, 'lon': trans.lon}
            out = xr.DataArray(dask.array.stack(grids_ll), coords=coords).rename(grids.name)

        # append source grid coordinates excluding removed y, x ones
        for (k,v) in grids.coords.items():
            if k not in ['y','x']:
                out[k] = v
        return out

##########################################################################################
# ll2ra
##########################################################################################
    def intf_ll2ra_matrix_parallel(self, pairs=None, chunksize=None, interactive=False):
        """
        Perform parallel computation of the geographic-to-radar coordinate transformation matrix.

        Parameters
        ----------
        pairs : list or None, optional
            List of interferogram pairs to process. If None, all available pairs will be processed.
        interactive : bool, optional
            Flag indicating whether to return the matrix without saving to a file.
        """
        import xarray as xr
        import numpy as np
        import dask
        import os

        if chunksize is None:
            chunksize = self.chunksize

        pairs = self.pairs(pairs)

        # find any one interferogram to define the grid
        intf = self.open_grids(pairs[:1], 'phasefilt')[0].astype(bool)
        dy = np.diff(intf.y)[0]
        dx = np.diff(intf.x)[0]
        #print ('dy, dx', dy, dx)

        # get transform table
        trans_inv = self.get_trans_dat_inv()
        trans_inv_dy = np.diff(trans_inv.y)[0]
        trans_inv_dx = np.diff(trans_inv.x)[0]

        # define transform spacing in radar coordinates
        step_y = int(np.round(dy / trans_inv_dy))
        step_x = int(np.round(dx / trans_inv_dx))
        #print ('step_y', step_y, 'step_x', step_x)

        # define the equally spacing geographic coordinates grid
        ys = trans_inv.y[step_y//2::step_y]
        xs = trans_inv.x[step_x//2::step_x]

        # decimate the full inverse trans grid to the required spacing
        trans = trans_inv.sel(y=ys, x=xs)[['lt', 'll']]
    
        if interactive:
            return trans

        # save to NetCDF file
        filename = self.get_filenames(None, None, 'intf_ll2ra')
        #print ('filename', filename)
        # to resolve NetCDF rewriting error
        if os.path.exists(filename):
            os.remove(filename)
        encoding = {var: self.compression(trans[var].shape, chunksize=chunksize) for var in trans.data_vars}
        handler = trans.to_netcdf(filename,
                                  encoding=encoding,
                                  engine=self.engine,
                                  compute=False)
        tqdm_dask(dask.persist(handler), desc='Build ll2ra Transform')
        handler.close()

    def get_intf_ll2ra(self, subswath=None, chunksize=None):
        """
        Get the geographic-to-radar coordinate transformation matrix.

        Parameters
        ----------
        chunksize : int or dict, optional
            Chunk size for dask arrays. If not provided, the default chunk size is used.

        Returns
        -------
        xarray.DataArray
            The radar-to-geographic coordinate transformation matrix.

        Notes
        -----
        This method retrieves the geographic-to-radar coordinate transformation matrix (intf_ll2ra) stored in the
        NetCDF grid. The matrix is useful for direct geocoding, converting geographic coordinate grids to
        radar coordinates interferogram grid.
        """
        import xarray as xr

        subswath = self.get_subswath(subswath)
        filename = self.get_filenames(subswath, None, 'intf_ll2ra')
        trans_inv = xr.open_dataset(filename, engine=self.engine, chunks=self.chunksize)
        return trans_inv

    def intf_ll2ra(self, grids, chunksize=None):
        """
        Perform inverse geocoding from geographic to radar coordinates.

        Parameters
        ----------
        grids : xarray.DataArray
            Grid(s) representing the interferogram(s) in radar coordinates.
        chunksize : int or dict, optional
            Chunk size for dask arrays. If not provided, the default chunk size is used.

        Returns
        -------
        xarray.DataArray
            The inverse geocoded grid(s) in geographic coordinates.

        Examples
        --------
        Inverse geocode 3D unwrapped phase grids stack:
        unwraps_ll = sbas.open_grids(pairs, 'unwrap', geocode=True)
        unwraps = sbas.intf_ll2ra(unwraps_ll)
        """
        import dask
        import xarray as xr
        import numpy as np

        # helper check
        if not 'lat' in grids.dims or not 'lon' in grids.dims:
            print ('NOTE: the input grid is not in geographic coordinates, miss inverse geocoding')
            return grids

        if chunksize is None:
            chunksize = self.chunksize

        @dask.delayed
        def intf_block_inv(trans_inv, grid_ll):
            from scipy.interpolate import RegularGridInterpolator

            # use trans table subset
            lt = trans_inv.lt.values.ravel()
            ll = trans_inv.ll.values.ravel()
            points = np.column_stack([lt, ll])

            # get interferogram full grid
            lats = grid_ll.lat.values
            lons = grid_ll.lon.values

            # calculate trans grid subset extent
            ltmin, ltmax = np.nanmin(lt), np.nanmax(lt)
            llmin, llmax = np.nanmin(ll), np.nanmax(ll)
            # and spacing
            dlat = np.diff(lats)[0]
            dlon = np.diff(lons)[0]

            # select required interferogram grid subset
            lats = lats[(lats>ltmin-dlat)&(lats<ltmax+dlat)]
            lons = lons[(lons>llmin-dlon)&(lons<llmax+dlon)]

            # for cropped interferogram we can have no valid pixels for the processing
            if lats.size == 0 or lons.size == 0:
                return np.nan * np.zeros((trans_inv.y.size, trans.x.size), dtype=np.float32)

            values = grid_ll.sel(lat=lats, lon=lons).values.astype(np.float64)

            # perform interpolation
            interp = RegularGridInterpolator((lats, lons), values, method='nearest', bounds_error=False)
            grid_ra = interp(points).reshape(trans_inv.y.size, trans_inv.x.size).astype(np.float32)

            return grid_ra

        # get transform table
        trans_inv = self.get_intf_ll2ra()[['lt', 'll']]
        ys = trans_inv.y
        xs = trans_inv.x
        # define processing blocks
        chunks = ys.size / chunksize
        xs_blocks = np.array_split(xs, np.arange(0, xs.size, chunksize)[1:])

        grids_ra = []
        # unify input grid(s) to stack
        for grid_ll in grids if len(grids.dims) == 3 else [grids]:
            # per-block processing
            blocks  = []
            for xs_block in xs_blocks:
                block = dask.array.from_delayed(intf_block_inv(trans_inv.sel(x=xs_block), grid_ll),
                                                shape=(ys.size, xs_block.size), dtype=np.float32)
                blocks.append(block)
            #grid_ll = dask.array.block(blocks)
            # set the output grid and drop the fake dimension if needed
            grid_ra = xr.DataArray(dask.array.block(blocks), coords=trans_inv.coords).rename(grids.name)
            grids_ra.append(grid_ra)

        if len(grids.dims) == 2:
            # drop the fake dimension
            coords = trans_inv.coords
            out = xr.DataArray(grids_ra[0], coords=coords).rename(grids.name)
        else:
            # find stack dim
            stack_dim = grids.dims[0]
            coords = {stack_dim: grids[stack_dim], 'y': trans_inv.y, 'x': trans_inv.x}
            out = xr.DataArray(dask.array.stack(grids_ra), coords=coords).rename(grids.name)

        # append source grid coordinates excluding removed lat, lon ones
        for (k,v) in grids.coords.items():
            if k not in ['lat','lon']:
                out[k] = v
        return out
