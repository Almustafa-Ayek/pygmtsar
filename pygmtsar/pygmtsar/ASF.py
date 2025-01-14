# ----------------------------------------------------------------------------
# PyGMTSAR
# 
# This file is part of the PyGMTSAR project: https://github.com/mobigroup/gmtsar
# 
# Copyright (c) 2023, Alexey Pechnikov
# 
# Licensed under the BSD 3-Clause License (see LICENSE for details)
# ----------------------------------------------------------------------------
from .tqdm_joblib import tqdm_joblib
from .S1 import S1

class ASF(tqdm_joblib):
    import pandas as pd
    from datetime import timedelta

    template_url = 'https://datapool.asf.alaska.edu/SLC/S{satellite}/{scene}.zip'
    template_safe = '*.SAFE/*/{mission}-iw{subswath}-slc-{polarization}-*'
    # check for downloaded scene files
    template_scene = 'S1?_IW_SLC__1S??_{start}_*.SAFE/*/s1?-iw{subswath_lowercase}-slc-{polarization_lowercase}-{start_lowercase}-*'

    def __init__(self, username=None, password=None):
        import asf_search
        import getpass
        if username is None:
            username = getpass.getpass('Please enter your ASF username and press Enter key:')
        if password is None:
            password = getpass.getpass('Please enter your ASF password and press Enter key:')
        self.username = username
        self.password = password

    def _get_asf_session(self):
        import asf_search
        return asf_search.ASFSession().auth_with_creds(self.username, self.password)

    def download(self, basedir, scenes_or_bursts, subswaths=None, polarization='VV', **kwargs):
        """
        Downloads the specified subswaths or bursts extracted from Sentinel-1 SLC scenes.
    
        Parameters
        ----------
        basedir : str
            The directory where the downloaded scenes will be saved.
        scenes_or_bursts : list of str
            List of scene and bursts identifiers to download.
        subswaths : list of str
            Number representing the subswaths to download for each scene (e.g., 1 or 123). Ignored if a burst ID is provided.
        polarization : str, optional
            The polarization to download ('VV' by default). Ignored if the burst ID is provided.
        session : asf_search.ASFSession, optional
            The session object for authentication. If None, a new session is created.
        n_jobs : int, optional
            The number of concurrent download jobs. Default is 8.
        joblib_backend : str, optional
            The backend for parallel processing. Default is 'loky'.
        skip_exist : bool, optional
            If True, skips downloading scenes that already exist. Default is True.
        debug : bool, optional
            If True, prints debugging information. Default is False.
    
        Returns
        -------
        pandas.DataFrame
            A DataFrame containing the list of downloaded scenes and bursts.
        """
        import pandas as pd

        bursts = [item for item in scenes_or_bursts if item.endswith('-BURST')]
        scenes = [item[:-4] if item.endswith('-SLC') else item for item in scenes_or_bursts if item not in bursts]

        results = []
        if len(bursts):
            result = self.download_bursts(basedir, bursts, **kwargs)
            if result is not None:
                results.append(result.rename({'burst': 'burst_or_scene'}, axis=1))
        if len(scenes):
            result = self.download_scenes(basedir, scenes, subswaths=subswaths, polarization=polarization, **kwargs)
            if result is not None:
                results.append(result.rename({'scene': 'burst_or_scene'}, axis=1))
        if len(results):
            return pd.concat(results)

    def download_scenes(self, basedir, scenes, subswaths, polarization='VV', session=None,
                        n_jobs=4, joblib_backend='loky', skip_exist=True, debug=False):
        """
        Downloads the specified subswaths extracted from Sentinel-1 SLC scenes.
    
        Parameters
        ----------
        basedir : str
            The directory where the downloaded scenes will be saved.
        scenes : list of str
            List of scene identifiers to download.
        subswaths : list of str
            Number representing the subswaths to download for each scene (e.g., 1 or 123).
        polarization : str, optional
            The polarization to download ('VV' by default).
        session : asf_search.ASFSession, optional
            The session object for authentication. If None, a new session is created.
        n_jobs : int, optional
            The number of concurrent download jobs. Default is 4.
        joblib_backend : str, optional
            The backend for parallel processing. Default is 'loky'.
        skip_exist : bool, optional
            If True, skips downloading scenes that already exist. Default is True.
        debug : bool, optional
            If True, prints debugging information. Default is False.
    
        Returns
        -------
        pandas.DataFrame
            A DataFrame containing the list of downloaded scenes.
        """
        import pandas as pd
        import numpy as np
        import asf_search
        import fnmatch
        import joblib
        from tqdm.auto import tqdm
        import os
        import re
        import glob
        from datetime import datetime, timedelta
        import warnings
        # supress asf_search 'UserWarning: File already exists, skipping download'
        warnings.filterwarnings("ignore", category=UserWarning)

        # create the directory if needed
        os.makedirs(basedir, exist_ok=True)

        # collect all the existing files once
        files = os.listdir(basedir)
        #print ('files', len(files))

        # skip existing scenes
        if skip_exist:
            # collect all the existing files once
            files = glob.glob('**', root_dir=basedir, recursive=True)
            #print ('files', len(files))
            # check scenes folders only
            #scenes_missed = np.unique([scene for scene in scenes if f'{scene}.SAFE' not in files])
            scenes_missed = []
            for scene in scenes:
                scene_path = '/'.join([scene + '.SAFE'] + self.template_scene.split('/')[1:])
                #print ('scene_path', scene_path)
                for subswath in str(subswaths):
                    pattern = scene_path.format(
                                         subswath_lowercase = subswath.lower(),
                                         polarization_lowercase = polarization.lower(),
                                         start_lowercase = '*')
                    #print ('pattern', pattern)
                    matching = [filename for filename in files if fnmatch.fnmatch(filename, pattern)]
                    exts = [os.path.splitext(fname)[1] for fname in matching]
                    if '.tiff' in exts and '.xml'in exts:
                        pass
                    else:
                        scenes_missed.append(scene)
    
        else:
            # process all the defined scenes
            scenes_missed = scenes
        #print ('scenes_missed', len(scenes_missed))

        # do not use internet connection, work offline when all the scenes already available
        if len(scenes_missed) == 0:
            return

        def get_url(scene):
            return self.template_url.format(satellite=scene[2:3], scene=scene)

        def get_patterns(subswaths, polarization, mission):
            #print (f'get_patterns: {subswaths}, {polarization}, {mission}')
            assert len(mission) == 3 and mission[:2]=='S1', \
                f'ERROR: mission name is invalid: {mission}. Expected names like "S1A", "S1B", etc.'
            outs = []
            for subswath in str(subswaths):
                pattern = self.template_safe.format(mission=mission.lower(),
                                                    subswath=subswath,
                                                    polarization=polarization.lower())
                outs.append(pattern)
            return outs

        def download_scene(scene, subswaths, polarization, basedir, session):
            # define scene zip url
            url = get_url(scene)
            #print (f'download_scene: {url}, {patterns}, {basedir}, {session}')
            patterns = get_patterns(subswaths, polarization, mission=scene[:3])
            #print ('patterns', patterns)
            with asf_search.remotezip(url, session) as remotezip:
                filenames = remotezip.namelist()
                #print ('filenames', filenames)
                for pattern in patterns:
                    #print ('pattern', pattern)
                    matching = [filename for filename in filenames if fnmatch.fnmatch(filename, pattern)]
                    for filename in matching:
                        filesize = remotezip.getinfo(filename).file_size
                        #print (filename, filesize)
                        fullname = os.path.join(basedir, filename)
                        if os.path.exists(fullname) and os.path.getsize(fullname) == filesize:
                            #print (f'pass {fullname}')
                            pass
                        else:
                            #print (f'download {fullname}')
                            # create the directory if needed
                            try:
                                os.makedirs(os.path.dirname(fullname), exist_ok=True)
                                if os.path.exists(fullname + '.tmp'):
                                    os.remove(fullname + '.tmp')
                                with open(fullname + '.tmp', 'wb') as file:
                                    file.write(remotezip.read(filename))
                                assert os.path.getsize(fullname + '.tmp') == filesize, \
                                    f'ERROR: Downloaded incomplete scene content'
                                os.rename(fullname + '.tmp', fullname)
                            except Exception as e:
                                print(e)
                                raise
                            finally:
                                if os.path.exists(fullname + '.tmp'):
                                    os.remove(fullname + '.tmp')
                            #remotezip.extract(filename, basedir)

        # prepare authorized connection
        if session is None:
            session = self._get_asf_session()

        if n_jobs is None or debug == True:
            print ('Note: sequential joblib processing is applied when "n_jobs" is None or "debug" is True.')
            joblib_backend = 'sequential'

        # download scenes
        with self.tqdm_joblib(tqdm(desc='ASF Downloading Sentinel-1 SLC:', total=len(scenes_missed))) as progress_bar:
            joblib.Parallel(n_jobs=n_jobs, backend=joblib_backend)(joblib.delayed(download_scene)\
                                    (scene, subswaths, polarization, basedir, session) for scene in scenes_missed)

        # parse processed scenes and convert to dataframe
        #print ('scenes', len(scenes))
        scenes_downloaded = pd.DataFrame(scenes_missed, columns=['scene'])
        # return the results in a user-friendly dataframe
        #scenes_downloaded['scene'] = scenes_downloaded.scene\
        #                             .apply(lambda name: self.template_url.format(satellite=name[2:3], scene=name))
        return scenes_downloaded

    # https://asf.alaska.edu/datasets/data-sets/derived-data-sets/sentinel-1-bursts/
    def download_bursts(self, basedir, bursts, session=None, n_jobs=8, joblib_backend='loky', skip_exist=True, debug=False):
        """
        Downloads the specified bursts extracted from Sentinel-1 SLC scenes.
    
        Parameters
        ----------
        basedir : str
            The directory where the downloaded bursts will be saved.
        bursts : list of str
            List of burst identifiers to download.
        session : asf_search.ASFSession, optional
            The session object for authentication. If None, a new session is created.
        n_jobs : int, optional
            The number of concurrent download jobs. Default is 8.
        joblib_backend : str, optional
            The backend for parallel processing. Default is 'loky'.
        skip_exist : bool, optional
            If True, skips downloading bursts that already exist. Default is True.
        debug : bool, optional
            If True, prints debugging information. Default is False.
    
        Returns
        -------
        pandas.DataFrame
            A DataFrame containing the list of downloaded bursts.
        """
        import rioxarray as rio
        from tifffile import TiffFile
        import xmltodict
        import pandas as pd
        import asf_search
        import joblib
        from tqdm.auto import tqdm
        import os
        import glob
        from datetime import datetime, timedelta
        import time
        import warnings
        # supress asf_search 'UserWarning: File already exists, skipping download'
        warnings.filterwarnings("ignore", category=UserWarning)
        # repeat failed downloads
        retries = 100
        retries_timeout = 2

        def filter_azimuth_time(items, start_utc_dt, stop_utc_dt, delta=3):
            return [item for item in items if
                 datetime.strptime(item['azimuthTime'], '%Y-%m-%dT%H:%M:%S.%f') >= start_utc_dt - timedelta(seconds=delta) and 
                 datetime.strptime(item['azimuthTime'], '%Y-%m-%dT%H:%M:%S.%f') <= stop_utc_dt + timedelta(seconds=delta)]

        # create the directory if needed
        os.makedirs(basedir, exist_ok=True)
    
        # skip existing bursts
        if skip_exist:
            bursts_missed = []
            for burst in bursts:
                #print (burst)
                burst_parts = burst.split('_')
                subswath = burst_parts[2]
                polarization = burst_parts[4]
                start = burst_parts[3]
                #print ('start', start, 'subswath', subswath, 'polarization', polarization)
                template = self.template_scene.format(start=start,
                                                     subswath_lowercase = subswath.lower(),
                                                     polarization_lowercase = polarization.lower(),
                                                     start_lowercase = start.lower())
                #print ('template', template)
                files = glob.glob(template, root_dir=basedir)
                exts =[ os.path.splitext(file)[-1] for file in files]
                if sorted(exts) == ['.tiff', '.xml']:
                    #print ('pass')
                    pass
                else:
                    bursts_missed.append(burst)
        else:
            # process all the defined scenes
            bursts_missed = bursts
        #print ('bursts_missed', len(bursts_missed))
        # do not use internet connection, work offline when all the scenes already available
        if len(bursts_missed) == 0:
            return
    
        def download_burst(result, basedir, session):
            properties = result.geojson()['properties']
            #print (properties)
            burstIndex = properties['burst']['burstIndex']
            platform = properties['platform'][-2:]
            polarization = properties['polarization']
            #print ('polarization', polarization)
            subswath = properties['burst']['subswath']
            #print ('subswath', subswath)
            # fake image number unique per polarizations
            # the real image number is sequential between all the polarizations
            # this trick allows to detect scene files without manifest downloading
            #imageNumber = '00' + subswath[-1:]
            #print ('imageNumber', imageNumber)
            # define new scene name
            scene = properties['url'].split('/')[3]
             #print ('scene', scene)
            # use fake start and stop times to follow the burst naming
            start_time = properties['sceneName'].split('_')[3]
            start_time_dt = datetime.strptime(start_time, '%Y%m%dT%H%M%S')
            stop_time_dt = (start_time_dt  + timedelta(seconds=3))
            stop_time = stop_time_dt.strftime('%Y%m%dT%H%M%S')
            #print ('start_time, stop_time', start_time, stop_time)
            scene_parts = scene.split('_')
            #scene_parts[5] = startTime.replace('-','').replace(':','')[:len(scene_parts[5])]
            scene_parts[5] = start_time
            #scene_parts[6] = stopTime.replace('-','').replace(':','')[:len(scene_parts[6])]
            scene_parts[6] = stop_time
            scene = '_'.join(scene_parts)
            #print ('scene', scene)
            scene_dir = os.path.join(basedir, scene + '.SAFE')
            # define burst name
            burst = '-'.join([f's{platform.lower()}-{subswath.lower()}-slc-{polarization.lower()}'] + scene_parts[5:-1] + ['001']).lower()
            # s1a-iw2-slc-vv-20240314t130744-20240314t130747-052978-0669c6-001
            #print ('burst', burst)
    
            # create the directories if needed
            tif_dir = os.path.join(scene_dir, 'measurement')
            xml_dir = os.path.join(scene_dir, 'annotation')
            # save annotation using the burst and scene names
            xml_file = os.path.join(xml_dir, burst + '.xml')
            #rint ('xml_file', xml_file)
            tif_file = os.path.join(tif_dir, burst + '.tiff')
            #print ('tif_file', tif_file)
            for dirname in [scene_dir, tif_dir, xml_dir]:
                os.makedirs(dirname, exist_ok=True)
    
            # download tif
            # properties['bytes'] is not an accurate file size but it looks about 40 kB smaller
            if os.path.exists(tif_file) and os.path.getsize(tif_file) >= int(properties['bytes']):
                #print (f'pass {tif_file}')
                pass
            else:
                #print ('YYY', os.path.getsize(tif_file), properties['bytes'])
                # remove potentially incomplete file if needed
                if os.path.exists(tif_file):
                    os.remove(tif_file)
                # check if we can open the downloaded file without errors
                tmp_file = os.path.join(scene_dir, os.path.basename(tif_file))
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
                # download burst tif file and save using the burst and scene names
                #result.download(os.path.dirname(tif_file), filename=os.path.basename(tif_file))
                for retry in range(retries):
                    try:
                        result.download(scene_dir, filename=os.path.basename(tif_file), session=session)
                        if not os.path.exists(tmp_file):
                            continue
                        # check file validity opening it
                        with rio.open_rasterio(tmp_file) as raster:
                            raster.load()
                            # TiFF file is well loaded
                            break
                    except Exception as e:
                        print(f"Failed attempt {retry+1} to download {tmp_file}: {e}")
                        time.sleep(retries_timeout)
                # check if the file is really downloaded
                assert os.path.exists(tmp_file), f'ERROR: TiFF file {tmp_file} is not downloaded and validated'
                # move to persistent name
                os.rename(tmp_file, tif_file)
        
            # download xml
            if os.path.exists(xml_file) and os.path.getsize(xml_file) > 0:
                #print (f'pass {xml_file}')
                pass
            else:
                # get TiFF file information
                with TiffFile(tif_file) as tif:
                    page = tif.pages[0]
                    offset = page.dataoffsets[0]
                #print ('offset', offset)
                
                # get the file name
                basename = os.path.basename(properties['additionalUrls'][0])
                #print ('basename', '=>', basename)
                manifest_file = os.path.join(scene_dir, basename)
                # remove potentially incomplete manifest file if needed
                if os.path.exists(manifest_file):
                    os.remove(manifest_file)
                # download and process manifest file even when it exists but is not processed to annotation xml
                for retry in range(retries):
                    try:
                        asf_search.download_urls(urls=properties['additionalUrls'], path=scene_dir, session=session)
                        if not os.path.exists(manifest_file):
                            continue
                        # parse xml
                        with open(manifest_file, 'r') as file:
                            _ = xmltodict.parse(file.read())['burst']['metadata']['product'][0]
                            # xml file is well parsed
                            break
                    except Exception as e:
                        print(f"Failed attempt {retry+1} to download and parse {manifest_file}: {e}")
                        time.sleep(retries_timeout)
                # check if the file is really downloaded
                assert os.path.exists(manifest_file), f'ERROR: manifest file {manifest_file} is not downloaded and validated'
                # parse xml
                with open(manifest_file, 'r') as file:
                    xml_content = file.read()
                # remove manifest file
                if os.path.exists(manifest_file):
                    os.remove(manifest_file)

                subswathidx = int(subswath[-1:]) - 1 
                content = xmltodict.parse(xml_content)['burst']['metadata']['product'][subswathidx]
                assert polarization == content['polarisation'], 'ERROR: XML polarization differs from burst polarization'
                annotation = content['content']

                annotation_burst = annotation['swathTiming']['burstList']['burst'][burstIndex]
                start_utc = annotation_burst['azimuthTime']
                start_utc_dt = datetime.strptime(start_utc, '%Y-%m-%dT%H:%M:%S.%f')
                #print ('start_utc', start_utc, start_utc_dt)
                
                length = annotation['swathTiming']['linesPerBurst']
                azimuth_time_interval = annotation['imageAnnotation']['imageInformation']['azimuthTimeInterval']
                burst_time_interval = timedelta(seconds=(int(length) - 1) * float(azimuth_time_interval))
                stop_utc_dt = start_utc_dt + burst_time_interval
                stop_utc = stop_utc_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
                #print ('stop_utc', stop_utc, stop_utc_dt)
                
                # output xml
                product = {}
                
                adsHeader = annotation['adsHeader']
                adsHeader['startTime'] = start_utc
                adsHeader['stopTime'] = stop_utc
                adsHeader['imageNumber'] = '001'
                product = product   | {'adsHeader': adsHeader}
                
                qualityInformation = {'productQualityIndex': annotation['qualityInformation']['productQualityIndex']} |\
                                      {'qualityDataList':     annotation['qualityInformation']['qualityDataList']}
                product = product   | {'qualityInformation': qualityInformation}

                generalAnnotation = annotation['generalAnnotation']
                # filter annotation['generalAnnotation']['replicaInformationList'] by azimuthTime
                product = product   | {'generalAnnotation': generalAnnotation}
                
                imageAnnotation = annotation['imageAnnotation']
                imageAnnotation['imageInformation']['productFirstLineUtcTime'] = start_utc
                imageAnnotation['imageInformation']['productLastLineUtcTime'] = stop_utc
                imageAnnotation['imageInformation']['productComposition'] = 'Assembled'
                imageAnnotation['imageInformation']['sliceNumber'] = '0'
                imageAnnotation['imageInformation']['sliceList'] = {'@count': '0'}
                imageAnnotation['imageInformation']['numberOfLines'] = str(length)
                # imageStatistics and inputDimensionsList are not updated
                product = product   | {'imageAnnotation': imageAnnotation}
                
                dopplerCentroid = annotation['dopplerCentroid']
                items = filter_azimuth_time(dopplerCentroid['dcEstimateList']['dcEstimate'], start_utc_dt, stop_utc_dt)
                dopplerCentroid['dcEstimateList'] = {'@count': len(items), 'dcEstimate': items}
                product = product   | {'dopplerCentroid': dopplerCentroid}
                
                antennaPattern = annotation['antennaPattern']
                items = filter_azimuth_time(antennaPattern['antennaPatternList']['antennaPattern'], start_utc_dt, stop_utc_dt)
                antennaPattern['antennaPatternList'] = {'@count': len(items), 'antennaPattern': items}
                product = product   | {'antennaPattern': antennaPattern}
                
                swathTiming = annotation['swathTiming']
                items = filter_azimuth_time(swathTiming['burstList']['burst'], start_utc_dt, start_utc_dt, 1)
                assert len(items) == 1, 'ERROR: unexpected bursts count, should be 1'
                # add TiFF file information
                items[0]['byteOffset'] = offset
                swathTiming['burstList'] = {'@count': len(items), 'burst': items}
                product = product   | {'swathTiming': swathTiming}
                
                geolocationGrid = annotation['geolocationGrid']
                items = filter_azimuth_time(geolocationGrid['geolocationGridPointList']['geolocationGridPoint'], start_utc_dt, stop_utc_dt, 1)
                # re-numerate line numbers for the burst
                for item in items: item['line'] = str(int(item['line']) - (int(length) * burstIndex))
                geolocationGrid['geolocationGridPointList'] = {'@count': len(items), 'geolocationGridPoint': items}
                product = product   | {'geolocationGrid': geolocationGrid}
                
                product = product   | {'coordinateConversion': annotation['coordinateConversion']}
                product = product   | {'swathMerging': annotation['swathMerging']}

                with open(xml_file, 'w') as file:
                    file.write(xmltodict.unparse({'product': product}, pretty=True, indent='  '))
    
        # prepare authorized connection
        if session is None:
            session = self._get_asf_session()
    
        with tqdm(desc=f'ASF Downloading Bursts Catalog', total=1) as pbar:
            results = asf_search.granule_search(bursts_missed)
            pbar.update(1)
    
        if n_jobs is None or debug == True:
            print ('Note: sequential joblib processing is applied when "n_jobs" is None or "debug" is True.')
            joblib_backend = 'sequential'

        # download bursts
        with self.tqdm_joblib(tqdm(desc='ASF Downloading Sentinel-1 Bursts', total=len(bursts_missed))) as progress_bar:
            joblib.Parallel(n_jobs=n_jobs, backend=joblib_backend)(joblib.delayed(download_burst)\
                                    (result, basedir, session) for result in results)
    
        # parse processed bursts and convert to dataframe
        bursts_downloaded = pd.DataFrame(bursts_missed, columns=['burst'])
        # return the results in a user-friendly dataframe
        return bursts_downloaded
