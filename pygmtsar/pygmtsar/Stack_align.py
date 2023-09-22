# ----------------------------------------------------------------------------
# PyGMTSAR
# 
# This file is part of the PyGMTSAR project: https://github.com/mobigroup/gmtsar
# 
# Copyright (c) 2021, Alexey Pechnikov
# 
# Licensed under the BSD 3-Clause License (see LICENSE for details)
# ----------------------------------------------------------------------------
from .Stack_dem import Stack_dem
from .PRM import PRM

class Stack_align(Stack_dem):

    def offset2shift(self, xyz, rmax, amax, method='linear'):
        """
        Convert offset coordinates to shift values on a grid.

        Parameters
        ----------
        xyz : numpy.ndarray
            Array containing the offset coordinates (x, y, z).
        rmax : int
            Maximum range bin.
        amax : int
            Maximum azimuth line.
        method : str, optional
            Interpolation method. Default is 'linear'.

        Returns
        -------
        xarray.DataArray
            Array containing the shift values on a grid.
        """
        import xarray as xr
        import numpy as np
        from scipy.interpolate import griddata

        # use center pixel GMT registration mode
        rngs = np.arange(8/2, rmax+8/2, 8)
        azis = np.arange(4/2, amax+4/2, 4)
        grid_r, grid_a = np.meshgrid(rngs, azis)

        grid = griddata((xyz[:,0], xyz[:,1]), xyz[:,2], (grid_r, grid_a), method=method)
        da = xr.DataArray(np.flipud(grid), coords={'y': azis, 'x': rngs}, name='z')
        return da

    # replacement for gmt grdfilter ../topo/dem.grd -D2 -Fg2 -I12s -Gflt.grd
    # use median decimation instead of average
    def get_topo_llt(self, subswath, degrees, geoloc=True, buffer_degrees=None, debug=False):
        """
        Get the topography coordinates (lon, lat, z) for decimated DEM.

        Parameters
        ----------
        subswath : int
            Subswath number.
        degrees : float
            Number of degrees for decimation.
        geoloc : bool, optional
            Flag indicating whether to perform geolocation. Default is True.
        debug : bool, optional
            Enable debug mode. Default is False.

        Returns
        -------
        numpy.ndarray
            Array containing the topography coordinates (lon, lat, z).
        """
        import xarray as xr
        import numpy as np

        # add buffer around the cropped area for borders interpolation
        dem_area = self.get_dem(subswath, geoloc=geoloc, buffer_degrees=buffer_degrees)
        ny = int(np.round(degrees/dem_area.lat.diff('lat')[0]))
        nx = int(np.round(degrees/dem_area.lon.diff('lon')[0]))
        if debug:
            print ('DEBUG: DEM decimation','ny', ny, 'nx', nx)
        dem_area = dem_area.coarsen({'lat': ny, 'lon': nx}, boundary='pad').mean()

        lats, lons, z = xr.broadcast(dem_area.lat, dem_area.lon, dem_area)
        topo_llt = np.column_stack([lons.values.ravel(), lats.values.ravel(), z.values.ravel()])
        return topo_llt

    # aligning for reference image
    def align_ref_subswath(self, subswath, debug=False):
        """
        Align and stack the reference scene.

        Parameters
        ----------
        subswath : int
            Subswath number.
        debug : bool, optional
            Enable debug mode. Default is False.

        Returns
        -------
        None

        Examples
        --------
        stack.stack_ref(subswath=2, debug=True)
        """
        import xarray as xr
        import numpy as np
        import os

        reference_line = list(self.get_reference(subswath).itertuples())[0]
        #print (reference_line)

        # for reference scene
        multistem, stem = self.multistem_stem(subswath, reference_line.datetime)
        path_stem = os.path.join(self.basedir, stem)
        path_multistem = os.path.join(self.basedir, multistem)

        # generate PRM, LED, SLC
        self.make_s1a_tops(subswath, debug=debug)

        PRM.from_file(path_stem + '.PRM')\
            .set(input_file = path_multistem + '.raw')\
            .update(path_multistem + '.PRM', safe=True)

        self.ext_orb_s1a(subswath, multistem, debug=debug)

        # recalculate after ext_orb_s1a
        earth_radius = PRM.from_file(path_multistem + '.PRM')\
            .calc_dop_orb(inplace=True).update().get('earth_radius')

    # aligning for secondary image
    def align_rep_subswath(self, subswath, date=None, degrees=12.0/3600, debug=False):
        """
        Align and stack secondary images.

        Parameters
        ----------
        subswath : int
            Subswath number.
        date : str or None, optional
            Date of the image to process. If None, process all images. Default is None.
        degrees : float, optional
            Degrees per pixel resolution for the coarse DEM. Default is 12.0/3600.
        debug : bool, optional
            Enable debug mode. Default is False.

        Returns
        -------
        None

        Examples
        --------
        stack.stack_rep(subswath=2, date='2023-05-01', degrees=15.0/3600, debug=True)
        """
        import xarray as xr
        import numpy as np
        import os
        
        # temporary filenames to be removed
        cleanup = []

        reference_line = list(self.get_reference(subswath).itertuples())[0]
        multistem, stem = self.multistem_stem(subswath, reference_line.datetime)
        #print (reference_line)

        # define reference image parameters
        # TODO: use reference PRM filename instead of subswath
        reference = self.PRM(subswath=subswath).sel('earth_radius').set(stem=stem, multistem=multistem)

        # prepare coarse DEM for alignment
        # 12 arc seconds resolution is enough, for SRTM 90m decimation is 4x4
        topo_llt = self.get_topo_llt(subswath, degrees=degrees)
        #topo_llt.shape

        line = list(self.get_repeat(subswath, date).itertuples())[0]
        multistem, stem = self.multistem_stem(subswath, line.datetime)
        #print (line)

        # define relative filenames for PRM
        stem_prm    = os.path.join(self.basedir, stem + '.PRM')
        mstem_prm   = os.path.join(self.basedir, multistem + '.PRM')
        reference_prm  = os.path.join(self.basedir, reference.get("stem") + '.PRM')
        mreference_prm = os.path.join(self.basedir, reference.get("multistem") + '.PRM')

        # TODO: define 1st image for line, in the example we have no more
        tmp_da = 0

        # generate PRM, LED
        self.make_s1a_tops(subswath, date, debug=debug)

        # compute the time difference between first frame and the rest frames
        t1, prf = PRM.from_file(stem_prm).get('clock_start', 'PRF')
        t2      = PRM.from_file(stem_prm).get('clock_start')
        nl = int((t2 - t1)*prf*86400.0+0.2)
        #echo "Shifting the reference PRM by $nl lines..."

        # Shifting the reference PRM by $nl lines...
        # shift the super-references PRM based on $nl so SAT_llt2rat gives precise estimate
        prm1 = PRM.from_file(reference_prm)
        prm1.set(prm1.sel('clock_start' ,'clock_stop', 'SC_clock_start', 'SC_clock_stop') + nl/prf/86400.0)
        tmp_prm = prm1

        # compute whether there are any image offset
        #if tmp_da == 0:
        # tmp_prm defined above from {reference}.PRM
        prm1 = tmp_prm.calc_dop_orb(reference.get('earth_radius'), inplace=True, debug=debug)
        prm2 = PRM.from_file(stem_prm).calc_dop_orb(reference.get('earth_radius'), inplace=True, debug=debug).update()
        lontie,lattie = prm1.SAT_baseline(prm2, debug=debug).get('lon_tie_point', 'lat_tie_point')
        tmp_am = prm1.SAT_llt2rat(coords=[lontie, lattie, 0], precise=1, debug=debug)[1]
        tmp_as = prm2.SAT_llt2rat(coords=[lontie, lattie, 0], precise=1, debug=debug)[1]
        # bursts look equal to rounded result int(np.round(...))
        tmp_da = int(tmp_as - tmp_am)
        #print ('tmp_am', tmp_am, 'tmp_as', tmp_as, 'tmp_da', tmp_da)

        # in case the images are offset by more than a burst, shift the super-reference's PRM again
        # so SAT_llt2rat gives precise estimate
        if abs(tmp_da) >= 1000:
            prf = tmp_prm.get('PRF')
            tmp_prm.set(tmp_prm.sel('clock_start' ,'clock_stop', 'SC_clock_start', 'SC_clock_stop') - tmp_da/prf/86400.0)
            #raise Exception('TODO: Modifying reference PRM by $tmp_da lines...')

        # tmp.PRM defined above from {reference}.PRM
        prm1 = tmp_prm.calc_dop_orb(reference.get('earth_radius'), inplace=True, debug=debug)
        tmpm_dat = prm1.SAT_llt2rat(coords=topo_llt, precise=1, debug=debug)
        prm2 = PRM.from_file(stem_prm).calc_dop_orb(reference.get('earth_radius'), inplace=True, debug=debug)
        tmp1_dat = prm2.SAT_llt2rat(coords=topo_llt, precise=1, debug=debug)

        # get r, dr, a, da, SNR table to be used by fitoffset.csh
        offset_dat0 = np.hstack([tmpm_dat, tmp1_dat])
        func = lambda row: [row[0],row[5]-row[0],row[1],row[6]-row[1],100]
        offset_dat = np.apply_along_axis(func, 1, offset_dat0)

        # define radar coordinates extent
        rmax, amax = PRM.from_file(stem_prm).get('num_rng_bins','num_lines')

        # prepare the offset parameters for the stitched image
        # set the exact borders in radar coordinates
        par_tmp = offset_dat[(offset_dat[:,0]>0) & (offset_dat[:,0]<rmax) & (offset_dat[:,2]>0) & (offset_dat[:,2]<amax)]
        par_tmp[:,2] += nl
        if abs(tmp_da) >= 1000:
            par_tmp[:,2] -= tmp_da
            par_tmp[:,3] += tmp_da

        # prepare the rshift and ashift look up table to be used by make_s1a_tops
        # use tmp_dat instead of offset_dat
        r_xyz = offset_dat[:,[0,2,1]]
        a_xyz = offset_dat[:,[0,2,3]]

        r_grd = self.offset2shift(r_xyz, rmax, amax)
        r_grd_filename = stem_prm[:-4]+'_r.grd'
        r_grd.to_netcdf(r_grd_filename, engine=self.engine)
        # drop the temporary file at the end of the function
        cleanup.append(r_grd_filename)

        a_grd = self.offset2shift(a_xyz, rmax, amax)
        a_grd_filename = stem_prm[:-4]+'_a.grd'
        a_grd.to_netcdf(a_grd_filename, engine=self.engine)
        # drop the temporary file at the end of the function
        cleanup.append(a_grd_filename)

        # generate the image with point-by-point shifts
        # note: it removes calc_dop_orb parameters from PRM file
        # generate PRM, LED
        self.make_s1a_tops(subswath,
                           date=line.Index, mode=1,
                           rshift_fromfile=f'{stem}_r.grd',
                           ashift_fromfile=f'{stem}_a.grd',
                           debug=debug)

        # need to update shift parameter so stitch_tops will know how to stitch
        PRM.from_file(stem_prm).set(PRM.fitoffset(3, 3, offset_dat)).update()

        # echo stitch images together and get the precise orbit
        # use stitch_tops tmp.stitchlist $stem to merge images

        # the raw file does not exist but it works
        PRM.from_file(stem_prm)\
            .set(input_file = f'{multistem}.raw')\
            .update(mstem_prm, safe=True)

        self.ext_orb_s1a(subswath, multistem, date=line.Index, debug=debug)

        # Restoring $tmp_da lines shift to the image... 
        PRM.from_file(mstem_prm).set(ashift=0 if abs(tmp_da) < 1000 else tmp_da, rshift=0).update()

        # that is safe to rewrite source files
        prm1 = PRM.from_file(mreference_prm)
        prm1.resamp(PRM.from_file(mstem_prm),
                    repeatSLC_tofile=mstem_prm[:-4]+'.SLC',
                    interp=1, debug=debug
        ).to_file(mstem_prm)

        PRM.from_file(mstem_prm).set(PRM.fitoffset(3, 3, par_tmp)).update()
        # TEST
        #prm1.set(PRM.fitoffset(3, 3, par_tmp)).update()

        PRM.from_file(mstem_prm).calc_dop_orb(reference.get('earth_radius'), 0, inplace=True, debug=debug).update()
        # TEST
        #prm1.calc_dop_orb(reference.get('earth_radius'), 0, inplace=True, debug=debug).update()
        
        # cleanup
        for filename in cleanup:
            #if os.path.exists(filename):
            os.remove(filename)

#     # merge_swath.c modified for SLCs
#     def merge_date(self, date, chunksize=None, debug=False):
#         import xarray as xr
#         import numpy as np
#         import os
#         from scipy import constants
# 
#         if chunksize is None:
#             chunksize = chunksize
# 
#         subswaths = self.get_subswaths()
# 
#         # define offset parameters to merge subswaths
#         prms = []
#         for subswath in subswaths:
#             #print (subswath)
#             prm = self.PRM(date, subswath=subswath)
#             prms.append(prm)
# 
#         assert len(np.unique([prm.get('PRF') for prm in prms])), 'Image PRFs are not consistent'
#         assert len(np.unique([prm.get('rng_samp_rate') for prm in prms])), 'Image range sampling rates are not consistent'
# 
#         heads = [0] + [((prm.get('clock_start') - prms[0].get('clock_start')) * 86400 * prms[0].get('PRF')).round().astype(int) for prm in prms[1:]]
#         # head123: 0, 466, -408
#         if debug:
#             print ('heads', heads)
#         # minh: -408
#         minh = min(heads)
#         if debug:
#             print ('minh', minh)
# 
#         #head123: 408, 874, 0
#         heads = np.asarray(heads) - minh
#         if debug:
#             print ('heads', heads)
# 
#         #ovl12,23: 2690, 2558
#         ovls = [prm1.get('num_rng_bins') - ((prm2.get('near_range') - prm1.get('near_range')) / (constants.speed_of_light/ prm1.get('rng_samp_rate') / 2)).round().astype(int) for (prm1, prm2) in zip(prms[:-1], prms[1:])]
#         if debug:
#             print ('ovls', ovls)
# 
#         #Writing the grid files..Size(69158x13075)...
#         #maxy: 13075
#         # TODO: disable offset 1
#         maxy = max([prm.get('num_valid_az') + head for prm, head in zip(prms, heads)]) + 1
#         # for SLC
#         #maxy = max([prm.get('num_valid_az') + head for prm, head in zip(prms, heads)])
#         if debug:
#             print ('maxy', maxy)
#         maxx = sum([prm.get('num_rng_bins') - ovl -1 for prm, ovl in zip(prms, [-1] + ovls)])
#         if debug:
#             print ('maxx', maxx)
# 
#         # disable heads shift
#         #head123: 467, 1, 875
#         #heads = [maxy - prm.get('num_valid_az') - head for prm, head in zip(prms, heads)]
#         #print ('heads', heads)
# 
#         #Stitching location n1 = 1045
#         #Stitching location n2 = 935
#         ns = [np.ceil(-prm.get('rshift') + prm.get('first_sample') + 150.0).astype(int) for prm in prms[1:]]
#         ns = [10 if n < 10 else n for n in ns]
#         if debug:
#             print ('ns', ns)
#         #ns [1070, 963]
#         
#         # TODO: add subswath_offset and subswath_head to PRM files
# 
#         # TEST: disable 1st subswath head offset to check phasediff
#         #heads[0] = 400
# 
#         # merge
#         slcs = []
#         # left and right coordinates for every subswath valid area
#         x1s = []
#         x2s = []
#         
#         # 1st
#         xlim = prms[0].get('num_rng_bins') - ovls[0] + ns[0]
#         x1s.append(0)
#         x2s.append(xlim)
#         # disable scaling
#         slc = prms[0].read_SLC_int(scale=None)
#         slc = slc.isel(x=slice(None,xlim)).assign_coords(y=slc.y + heads[0])
#         slcs.append(slc)
# 
#         # 2nd
#         if len(prms) == 2:
#             # TODO: check for 2 subswaths
#             xlim = -1
#         else:
#             # for 3 subswaths
#             xlim = prms[1].get('num_rng_bins') - ovls[1] + ns[1]
#         x1s.append(ns[0])
#         x2s.append(xlim)
#         # disable scaling
#         slc = prms[1].read_SLC_int(scale=None)
#         slc = slc.isel(x=slice(ns[0],xlim)).assign_coords(y=slc.y + heads[1])
#         slcs.append(slc)
# 
#         # 3rd
#         if len(prms) == 3:
#             # disable scaling
#             slc = prms[2].read_SLC_int(scale=None)
#             x1s.append(ns[1])
#             x2s.append(-2)
#             slc = slc.isel(x=slice(ns[1],-2)).assign_coords(y=slc.y + heads[2])
#             slcs.append(slc)
# 
#         # check and merge SLCs
#         assert maxx == sum([slc.x.size for slc in slcs]), 'Incorrect output grid range dimension size'
#         slc = xr.concat(slcs, dim='x', fill_value=0).assign_coords(x=0.5 + np.arange(maxx))
#         assert slc.y.size == maxy, 'Incorrect output grid azimuth dimension size'
#         assert slc.x.size == maxx, 'Incorrect output grid range dimension sizes'
# 
#         # define merge filenames
#         subswath = ''.join(map(str, subswaths))
#         line = self.get_repeat(subswaths[0], date).iloc[0]
#         multistem, stem = self.multistem_stem(subswath, line.datetime)
#         #print (multistem, stem)
#         prm_filename = os.path.join(self.basedir, multistem + '.PRM')
#         if debug:
#             print ('prm_filename', prm_filename)
# 
#         # merge PRM
#         prm = PRM(prms[0])
#         dt = -minh / prm.get('PRF') / 86400
#         prm = prm.set(SLC_file=multistem + '.SLC',
#                       num_lines=maxy, nrows=maxy, num_valid_az=maxy,
#                       num_rng_bins=maxx, bytes_per_line=4*maxx, good_bytes=4*maxx,
#                       SC_clock_start=prm.get('SC_clock_start') - dt,
#                       clock_start=prm.get('clock_start') - dt,
#                       SC_clock_stop=prm.get('SC_clock_start') + maxy / prm.get('PRF') / 86400,
#                       clock_stop=prm.get('clock_start') + maxy / prm.get('PRF') / 86400)\
#                       .calc_dop_orb(prm.get('earth_radius'), 0, inplace=True, debug=debug)\
#                       .to_file(prm_filename)
# 
# #         # merge PRM - test updating parameters for the central area
# #         prm = PRM(prms[0])
# #         dt = -minh / prm.get('PRF') / 86400
# #         near_range      = np.mean([prm.get('near_range') for prm in prms])
# #         SC_vel          = np.mean([prm.get('SC_vel') for prm in prms])
# #         SC_height       = np.mean([prm.get('SC_height') for prm in prms])
# #         SC_height_start = prms[0].get('SC_height_start')
# #         SC_height_end   = prms[-1].get('SC_height_end')
# #         prm = prm.set(SLC_file=multistem + '.SLC',
# #                       num_lines=maxy, nrows=maxy, num_valid_az=maxy,
# #                       num_rng_bins=maxx, bytes_per_line=4*maxx, good_bytes=4*maxx,
# #                       SC_clock_start=prm.get('SC_clock_start') - dt,
# #                       clock_start=prm.get('clock_start') - dt,
# #                       SC_clock_stop=prm.get('SC_clock_start') + maxy / prm.get('PRF') / 86400,
# #                       clock_stop=prm.get('clock_start') + maxy / prm.get('PRF') / 86400,
# #                       near_range=near_range, SC_vel=SC_vel, SC_height=SC_height,
# #                       SC_height_start=SC_height_start, SC_height_end=SC_height_end).to_file(prm_filename)
#         #return prm, slc
#         # save merged SLC
#         prm.write_SLC_int(slc, chunksize=chunksize)
# 
#         # add calculated offsets to single subswaths
#         for idx, prm in enumerate(prms):
#             prm.set(smath_maxy=maxy, swath_maxx=maxx,
#                     swath_minh=minh, swath_head=heads[idx],
#                     swath_left=x1s[idx], swath_right=x2s[idx]).update()
# 
#         # cleanup
#         # [os.path.join(self.basedir, prm.get('led_file')) for prm in prms]
#         # [prm.filename for prm in prms]
#         cleanup = [os.path.join(self.basedir, prm.get('SLC_file')) for prm in prms]
#         for filename in cleanup:
#             if debug:
#                 print ('DEBUG: remove', filename)
#             os.remove(filename)

    # define bottoms from reference scene and apply for all scenes
    def align_subswaths(self, date, offsets=None, chunksize=None, debug=False):
        import xarray as xr
        import numpy as np
        from scipy import constants

        if chunksize is None:
            chunksize = chunksize

        subswaths = self.get_subswaths()

        # define offset parameters to merge subswaths
        prms = []
        for subswath in subswaths:
            #print (subswath)
            prm = self.PRM(date, subswath=subswath)
            prms.append(prm)

        assert len(np.unique([prm.get('PRF') for prm in prms])), 'Image PRFs are not consistent'
        assert len(np.unique([prm.get('rng_samp_rate') for prm in prms])), 'Image range sampling rates are not consistent'

        if offsets is None:
            bottoms = [0] + [((prm.get('clock_start') - prms[0].get('clock_start')) * 86400 * prms[0].get('PRF')).round().astype(int) for prm in prms[1:]]
            # head123: 0, 466, -408
            if debug:
                print ('bottoms init', bottoms)
            # minh: -408
            minh = min(bottoms)
            if debug:
                print ('minh', minh)
            #head123: 408, 874, 0
            bottoms = np.asarray(bottoms) - minh
        else:
            bottoms = offsets['bottoms']
            minh = offsets['bottom']
        if debug:
            print ('bottoms', bottoms)

        #ovl12,23: 2690, 2558
        ovls = [prm1.get('num_rng_bins') - ((prm2.get('near_range') - prm1.get('near_range')) \
                    / (constants.speed_of_light/ prm1.get('rng_samp_rate') / 2)).round().astype(int) \
                for (prm1, prm2) in zip(prms[:-1], prms[1:])]
        if debug:
            print ('ovls', ovls)

        #Writing the grid files..Size(69158x13075)...
        #maxy: 13075
        # for SLC
        maxy = max([prm.get('num_valid_az') + bottom for prm, bottom in zip(prms, bottoms)])
        if debug:
            print ('maxy', maxy)
        maxx = sum([prm.get('num_rng_bins') - ovl -1 for prm, ovl in zip(prms, [-1] + ovls)])
        if debug:
            print ('maxx', maxx)

        #Stitching location n1 = 1045
        #Stitching location n2 = 935
        ns = [np.ceil(-prm.get('rshift') + prm.get('first_sample') + 150.0).astype(int) for prm in prms[1:]]
        ns = [10 if n < 10 else n for n in ns]
        if debug:
            print ('ns', ns)
        #ns [1070, 963]

        # left and right coordinates for every subswath valid area
        x1s = []
        x2s = []

        # 1st
        xlim = prms[0].get('num_rng_bins') - ovls[0] + ns[0]
        x1s.append(0)
        x2s.append(xlim)

        # 2nd
        if len(prms) == 2:
            xlim = prms[1].get('num_rng_bins') - 1
        else:
            # for 3 subswaths
            xlim = prms[1].get('num_rng_bins') - ovls[1] + ns[1]
        x1s.append(ns[0])
        x2s.append(xlim)

        # 3rd
        if len(prms) == 3:
            xlim = prms[2].get('num_rng_bins') - 2
            x1s.append(ns[1])
            x2s.append(xlim)

        # check and merge SLCs
        sumx = sum([right-left for right, left in zip(x2s, x1s)])
        if debug:
            print ('assert maxx == sum(...)', maxx, sumx)
        assert maxx == sumx, 'Incorrect output grid range dimension size'
    
        return {'bottoms': bottoms, 'lefts': x1s, 'rights': x2s, 'bottom': minh, 'extent': [maxy, maxx]}

    # merge_swath.c modified for SLCs
    # use reference scene vertical subswath aligments
    def merge_subswaths(self, date, offsets=None, chunksize=None, debug=False):
        import xarray as xr
        import numpy as np
        import os

        subswaths = self.get_subswaths()

        offsets = self.align_subswaths(date, offsets=offsets, chunksize=chunksize, debug=debug)
        if debug:
            print ('offsets', offsets)
        maxy = offsets['extent'][0]
        maxx = offsets['extent'][1]
        minh = offsets['bottom']
        bottoms = offsets['bottoms']
        lefts = offsets['lefts']
        rights = offsets['rights']

        slcs = []
        prms = []
        for subswath, bottom, left, right in zip(subswaths, bottoms, lefts, rights):
            prm = self.PRM(date, subswath=subswath)
            # disable scaling
            slc = prm.read_SLC_int(scale=None)
            slc = slc.isel(x=slice(left, right)).assign_coords(y=slc.y + bottom)
            slcs.append(slc)
            prms.append(prm)
    
        # check and merge SLCs, use zero fill for np.int16 datatype
        slc = xr.concat(slcs, dim='x', fill_value=0).assign_coords(x=0.5 + np.arange(maxx))

        if debug:
            print ('assert slc.y.size == maxy', slc.y.size, maxy)
        assert slc.y.size == maxy, 'Incorrect output grid azimuth dimension size'
        if debug:
            print ('assert slc.x.size == maxx', slc.x.size, maxx)
        assert slc.x.size == maxx, 'Incorrect output grid range dimension sizes'
        del slcs

        # define merge filenames  
        filename = prms[0].filename[:-5] + ''.join(map(str, subswaths))
        prm_filename = filename + '.PRM'
        slc_filename = os.path.basename(filename + '.SLC')
        if debug:
            print ('prm_filename', prm_filename, 'slc_filename', slc_filename)

        # merge PRM
        prm = PRM(prms[0])
        dt = -minh / prm.get('PRF') / 86400
        prm = prm.set(SLC_file=slc_filename,
                      num_lines=maxy, nrows=maxy, num_valid_az=maxy,
                      num_rng_bins=maxx, bytes_per_line=4*maxx, good_bytes=4*maxx,
                      SC_clock_start=prm.get('SC_clock_start') - dt,
                      clock_start=prm.get('clock_start') - dt,
                      SC_clock_stop=prm.get('SC_clock_start') + maxy / prm.get('PRF') / 86400,
                      clock_stop=prm.get('clock_start') + maxy / prm.get('PRF') / 86400)\
                 .to_file(prm_filename)
        #.calc_dop_orb(prm.get('earth_radius'), 0, inplace=True, debug=debug)\
    
        # add PRM to grid
        slc.attrs['prm'] = str(prm)
    
        # save merged SLC
        prm.write_SLC_int(slc, chunksize=chunksize)
        #return slc

        # add calculated offsets to single subswaths
        for idx, prm in enumerate(prms):
            prm.set(smath_maxy=maxy, swath_maxx=maxx,
                    swath_bottom=bottoms[idx],
                    swath_left=lefts[idx], swath_right=rights[idx]).update()

        # cleanup
        # [os.path.join(self.basedir, prm.get('led_file')) for prm in prms]
        # [prm.filename for prm in prms]
        cleanup = [os.path.join(self.basedir, prm.get('SLC_file')) for prm in prms]
        for filename in cleanup:
            if debug:
                print ('DEBUG: remove', filename)
            os.remove(filename)

    def align(self, dates=None, n_jobs=-1, **kwargs):
        """
        Stack and align scenes.

        Parameters
        ----------
        dates : list or None, optional
            List of dates to process. If None, process all scenes. Default is None.
        n_jobs : int, optional
            Number of parallel processing jobs. n_jobs=-1 means all processor cores are used. Default is -1.

        Returns
        -------
        None

        Examples
        --------
        stack.align()
        """
        import geopandas as gpd
        from tqdm.auto import tqdm
        import joblib

        if dates is None:
            dates = self.df.index.unique()
        dates_rep = [date for date in dates if date != self.reference]

        subswaths = self.get_subswaths()

        # prepare reference scene
        #self.stack_ref()
        with self.tqdm_joblib(tqdm(desc='Reference Frame', total=len(subswaths))) as progress_bar:
            joblib.Parallel(n_jobs=n_jobs)(joblib.delayed(self.align_ref_subswath)(subswath, **kwargs) for subswath in subswaths)

        # prepare secondary images
        with self.tqdm_joblib(tqdm(desc='Aligning Frames', total=len(dates_rep)*len(subswaths))) as progress_bar:
            joblib.Parallel(n_jobs=n_jobs)(joblib.delayed(self.align_rep_subswath)(subswath, date, **kwargs) \
                                           for date in dates_rep for subswath in subswaths)

        if len(subswaths) == 1:
            return

        # merge subswaths
        offsets = self.align_subswaths(self.reference)
        
        # TODO
        for date in dates:
            self.merge_subswaths(date, offsets=offsets, **kwargs)

#         with self.tqdm_joblib(tqdm(desc=f'Merging Subswaths', total=len(dates))) as progress_bar:
#             joblib.Parallel(n_jobs=n_jobs)(joblib.delayed(self.merge_date)(date, **kwargs) \
#                                            for date in dates)

        df = self.df.groupby(self.df.index).agg({'datetime': min, 'orbit': min, 'mission': min, 'polarization':min,
                                            'subswath': lambda s: int(''.join(map(str,list(s)))),
                                            'datapath': lambda p: list(p),
                                            'metapath': lambda p: list(p),
                                            'orbitpath': min,
                                            'geometry': lambda g: g.unary_union
                                           })
        self.df = gpd.GeoDataFrame(df)
        