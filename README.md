[![GMTSAR tests](https://github.com/mobigroup/gmtsar/actions/workflows/gmtsar.yml/badge.svg)](https://github.com/mobigroup/gmtsar/actions/workflows/gmtsar.yml)
[![MacOS tests](https://github.com/mobigroup/gmtsar/actions/workflows/macos.yml/badge.svg)](https://github.com/mobigroup/gmtsar/actions/workflows/macos.yml)
[![Ubuntu tests](https://github.com/mobigroup/gmtsar/actions/workflows/ubuntu.yml/badge.svg)](https://github.com/mobigroup/gmtsar/actions/workflows/ubuntu.yml)
[![PyPI tests](https://github.com/mobigroup/gmtsar/actions/workflows/pypi.yml/badge.svg)](https://github.com/mobigroup/gmtsar/actions/workflows/pypi.yml)
[![Available on pypi](https://img.shields.io/pypi/v/pygmtsar.svg)](https://pypi.python.org/pypi/pygmtsar/)
[![Docker](https://badgen.net/badge/icon/docker?icon=docker&label)](https://hub.docker.com/r/mobigroup/pygmtsar)

## PyGMTSAR (Python GMTSAR) - Sentinel-1 Satellite Interferometry For Everyone

<img src="https://user-images.githubusercontent.com/7342379/194891967-be2b56b5-c30c-4040-8ef8-39b448ce2390.jpg" style="zoom:24%;" />

This repository based on forked original GMTSAR and extended by my patches to binary tools and Python library PyGMTSAR. I commit my changes to binary tools to GMTSAR upstream and so it's possible to use the original GMTSAR master branch installation plus PyGMTSAR Python package via PIP. The project documentation including installation instructions available by the link: https://mobigroup.github.io/gmtsar/

The goal of the project is easy and fast satellite interferometry (InSAR) processing for Sentinel-1 radar scenes everywhere as on localhost as on cloud environments like to Google Cloud VM and AI Notebooks and Amazon EC2 and on free of charge cloud environment Google Colab and in Docker images. GMTSAR binary command line tools are used under the hood but all GMTSAR scripts and GMT command replaced by Python code using modern and robust algorithms.

### Live Examples in Docker image

Configure your Docker runtime (Preferences -> Resources tab for Docker Desktop) to use 2 CPU cores and 8 GB RAM or 4 CPU cores and 16 GB RAM and so on. Download the Docker image (or build it yourself using the Dockerfile in the repository) and run the container forwarding port 8888 to JupyterLab using this commands inside your command line terminal window:

```
docker pull mobigroup/pygmtsar

docker run -dp 8888:8888 --name pygmtsar docker.io/mobigroup/pygmtsar

docker logs pygmtsar
```

See the output for the JupyterLab link and copy and past it into your web browser address line. Also, the donwloaded Docker image can be started in Docker Desktop app - press "RUN" button and define the container name and the port in the opened dialog window (see "Optional settings" for the port number input field) and click on the newly created container to launch it and see the output log with the clickable link.

### Live Examples on Google Colab

The notebooks are interactive examples available directly in your web browser. All the steps automated including the software installation on Google Colab cloud host and downloading of Sentinel-1 orbit files, SRTM DEM (and its conversion to ellispoidal heights using EGM96 model), a landmask (to mask low-coherence water surfaces), Sentinel-1 SLC scenes from Alaska Satellite Facility (ASF) datastore and, of course, the complete interferometry processing and the results mapping.

#### Notebooks on Google Colab to Compare Results to GMTSAR, SNAP and GAMMA Software

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/12LJqlZNBUmvLlRl98rRFCbKveVPg9Ami?usp=sharing) **ASF Downloading 2017 Iran–Iraq Earthquake vs GMTSAR GAMMA SNAP Co-Seismic Interferogram** The notebook **downloads Sentinel-1 Scenes from Alaska Satellite Facility (ASF)** and **compares the results to GMTSAR, SNAP and GAMMA Software**. Note: replace the scene names to produce an **interferogram** and **LOS displacement** for your area of interest.

<img src="https://user-images.githubusercontent.com/7342379/177748605-788889e5-9afd-44d8-bc3c-dc6efe920ea0.png" width="50%">

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1PyYcxvuyzhh-g4NQEbKjcfTDQhREZInn?usp=sharing) **Live Example S1A_2016_Kumamoto Earthquake_Co-Seismic Interferogram vs ESA Sentinel 1 Toolbox on Alaska Satellite Facility**. This is a single subswath processing with **landmask** applied to **interferogram**, **unwapped phase**, and **LOS, east-west, vertical displacement** results.

<img src="https://user-images.githubusercontent.com/7342379/183805898-d7c1ad76-822e-428e-9259-f19cc9e7540e.jpg" width="50%">

<img src="https://user-images.githubusercontent.com/7342379/183816622-1dacce7e-6a2f-46b9-8e67-d701f55bdd30.png" width="50%">

<img src="https://user-images.githubusercontent.com/7342379/183649417-7fcb7f3f-8c8d-45e8-a2c9-9293498ebada.png" width="50%">

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1ZTPV4HY-UoLvDYVx0UGh_Z3B12scSh9E?usp=sharing) **Live Example S1AB 2021 Crete Earthquake Co-Seismic Interferogram vs Centre of EO Research & Satellite Remote Sensing, Greece Report** This is a single **cropped subswath** processing with **landmask** applied to **interferogram**, **unwapped phase**, and **LOS, east-west, vertical displacement** results.

<img src="https://user-images.githubusercontent.com/7342379/177004287-cdd4351c-0834-42ae-8e46-9da5e8b124bf.jpg" width="50%">

<img src="https://user-images.githubusercontent.com/7342379/183645260-f8529ff3-b014-499e-ba2f-ebea4937b2c2.png" width="50%">

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1sljxm2jAMGXynq4EYam6Siz8OLcPLN0h?usp=sharing) **GMTSAR example dataset S1A_Stack_CPGF_T173** This example illustrates **SBAS** and **PSI** analyses and **detrending** approach to remove **atmospheric noise** to produce much better results.

<img src="https://user-images.githubusercontent.com/7342379/135814732-aa0eb142-ae54-4a57-b271-c33b5174a28e.png" width="50%">

<img src="https://user-images.githubusercontent.com/7342379/189961167-bf3901e5-417c-41ce-a5ca-d1c74c239a04.png" width="50%">

#### More Complex Notebooks Still Available on Google Colab

The notebooks processing more than a single subswath or scene. It's possible on Google Colab limited resources using prepared datasets produced by PyGMTSAR "backup" command described in the notebooks.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1ZBVwlkiXMhSDS96oojpWrzTyRFIxv8Rp?usp=sharing) **ASF Downloading 2020 Ardabil, Iran Earthquake Co-Seismic Interferogram and LOS Displacement** The notebook **downloads Sentinel-1 Scenes from Alaska Satellite Facility (ASF)** to **crop the area** and **merge subswaths** and **detrend** results. Note: replace the scene names to produce an interferogram for your area of interest.

<img src="https://user-images.githubusercontent.com/7342379/194813466-fc4734a3-770d-4d6e-8012-91a4e5d781ba.png" width="50%">

<img src="https://user-images.githubusercontent.com/7342379/190451656-386d6cb8-f536-447c-8274-71d4f0435408.png" width="50%">

#### Long Timeseries Analysis is not available on Google Colab 

See a separate GitHub repository for Yamchi Dam area dynamic model [YamchiDam](https://github.com/mobigroup/YamchiDam) Here two of my software tools [PyGMTSAR](https://github.com/mobigroup/gmtsar) [N-Cube ParaView plugin for 3D/4D GIS Data Visualization](https://github.com/mobigroup/ParaView-plugins) are combined together for 4D analysis and visualization:

<img src="https://user-images.githubusercontent.com/7342379/144747743-a24d72ec-8875-4272-91f9-ec1f937bb798.gif" width="50%">

### About me

I have STEM master's degree in radio physics and in 2004 I was awarded first prize of the All-Russian Physics competition for significant results in Inverse modeling for non-linear optics and holography, also applicable for Inverse Modeling of Gravity, Magnetic, and Thermal fields. To create laser-induced holograms in non-linear optical composites I worked on interferograms numerical modeling and development of satellite interferometry processing software is very close task and so I build PyGMTSAR. Also, that's the related to inverse modeling of potensial fields like to gravity and I build Geomed3D geophisical modeling software too. In addition to my fundamental science knowledge, I’m world class data scientist and software developer with 20 years experience in science and industrial development. I have worked on government contracts and universities projects and on projects for LG Corp, Google Inc, etc. You are able to find some of my software and results on LinkedIn and GitHub and Upwork, see the links below. By the way, I left Russia many years ago and I work remotely for about 20 years.

To order some research, development and support see my profile on freelance platform [Upwork](https://www.upwork.com/freelancers/~01e65e8e7221758623) And of cource you are able to use my Open Source software for you scientific research and geological exploration projects and beyond.

 [Geological models on YouTube channel](https://www.youtube.com/channel/UCSEeXKAn9f_bDiTjT6l87Lg)

 [Augmented Reality (AR) Geological Models](https://mobigroup.github.io/ParaView-Blender-AR/)

 [GitHub repositories](https://github.com/mobigroup)

 [English posts and articles on LinkedIn](https://www.linkedin.com/in/alexey-pechnikov/)

[Russian articles on Habr](https://habr.com/ru/users/N-Cube/posts/)

@ Alexey Pechnikov, 2022
