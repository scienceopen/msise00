#!/usr/bin/env python3
"""
NOTE: The performance of this demo has not been checked at all.
Please do basic sanity checks of output.
Quick demo of calling NRL MSISE-00 using f2py3 from Python
Michael Hirsch
bostonmicrowave.com

Original fortran code from
http://nssdcftp.gsfc.nasa.gov/models/atmospheric/msis/nrlmsise00/
"""
from __future__ import division, print_function, absolute_import
from pandas import DataFrame, Panel4D, date_range
from numpy import arange, meshgrid, empty, atleast_1d,atleast_2d
from dateutil.parser import parse
from datetime import timedelta,datetime, time
from pytz import UTC
from astropy.time import Time
from astropy.coordinates import get_sun,EarthLocation, AltAz
from matplotlib.pyplot import figure,show, subplots, close
from matplotlib.ticker import ScalarFormatter
from tempfile import gettempdir
import sys
sys.path.append('../python-mapping')
from coordconv3d import aer2geodetic
#
import gtd7

def testgtd7(dtime,altkm,glat,glon,f107a,f107,ap,mass):
    glat = atleast_2d(glat); glon=atleast_2d(glon) #has to be here
#%% altitude 1-D
    if glat.size==1 and glon.size==1:
        densd,tempd = rungtd1d(dtime,altkm,glat,glon,f107a,f107,ap,mass)
#%% lat/lon grid at 1 altitude
    else: #I didn't use numpy.nditer just yet
        species = ['He','O','N2','O2','Ar','Total','H','N','AnomalousO']
        ttypes = ['exotemp','heretemp']
        dtime = atleast_1d(dtime) #keep for code reuse
        iyd,utsec,stl = datetime2gtd(dtime,glon)

        dens = empty((dtime.size,9,glat.shape[0],glat.shape[1]))
        temp = empty((dtime.size,2,glat.shape[0],glat.shape[1]))

        gtd7.meters(1) # makes output in m^-3 and kg/m^-3
        for k in range(dtime.size):
          for i in range(glat.shape[0]):
              for j in range(glat.shape[1]):
                dens[k,:,i,j], temp[k,:,i,j] = gtd7.gtd7(iyd[k],utsec[k],altkm,
                                       glat[i,j],glon[i,j],stl[k],f107a,f107,ap,mass)

        densd = Panel4D(dens, labels=dtime,items=species,major_axis=glat[:,0],minor_axis=glon[0,:])
        tempd = Panel4D(temp, labels=dtime,items=ttypes, major_axis=glat[:,0],minor_axis=glon[0,:])

    return densd,tempd

def rungtd1d(dtime,altkm,glat,glon,f107a,f107,ap,mass):
    species = ['He','O','N2','O2','Ar','Total','H','N','AnomalousO']
    ttypes = ['exotemp','heretemp']
    iyd,utsec,stl = datetime2gtd(dtime,glon)

    altkm = atleast_1d(altkm)
    dens = empty((altkm.size,9)); temp=empty((altkm.size,2))

    gtd7.meters(1) # makes output in m^-3 and kg/m^-3
    for i,a in enumerate(altkm):
        dens[i,:],temp[i,:] = gtd7.gtd7(iyd,utsec,a,glat,glon,stl, f107a,f107, ap,mass)

    densd = DataFrame(dens, index=altkm, columns=species)
    tempd = DataFrame(temp, index=altkm, columns=ttypes)
    return densd,tempd

def datetime2gtd(dtime,glon):
    """
    Inputs:
    dtime: Numpy 1-D array of datetime.datetime
    glon: Numpy 2-D array of geodetic longitudes

    Outputs:
    iyd: day of year
    utsec: seconds from midnight utc
    stl: local solar time
    """
    dtime = atleast_1d(dtime); glon=atleast_2d(glon)
    iyd=empty(dtime.size); utsec=empty(dtime.size)
    stl = empty((dtime.size,glon.shape[0],glon.shape[1]))

    for i,t in enumerate(dtime):
        t = forceutc(t)
        iyd[i] = int(t.strftime('%j'))
        #seconds since utc midnight
        utsec[i] = timedelta.total_seconds(t-datetime.combine(t.date(),time(0,tzinfo=UTC)))

        stl[i,...] = utsec[i]/3600 + glon/15 #FIXME let's be sure this is appropriate
    return iyd,utsec,stl

def forceutc(t):
    """
    input: python datetime (naive, utc, non-utc)
    output: utc datetime
    """
    if t.tzinfo == None:
        t = t.replace(tzinfo = UTC)
    else:
        t = t.astimezone(UTC)
    return t

def plotgtd(dens,temp,dtime,altkm, ap, f107,glat,glon):
    rodir = gettempdir()
    sfmt = ScalarFormatter(useMathText=True) #for 10^3 instead of 1e3
    sfmt.set_powerlimits((-2, 2))
    sfmt.set_scientific(True)
    sfmt.set_useOffset(False)

    if dens.ndim==2: #altitude 1-D
        footer = '\nlat/lon ' +str(glat) +'/'+str(glon) +'  Ap='+str(ap[0]) + '  F10.7='+str(f107)
        ax = figure().gca()
        for g in dens.columns:
            if g != 'Total':
                ax.semilogx(dens[g], dens.index, label=g)
        ax.legend(loc='best')
        ax.set_xlim(left=1e3)
        ax.set_ylabel('altitude [km]')
        ax.set_xlabel('density [m$^{-3}$]')
        ax.grid(True)
        ax.set_title('Number Density from MSISE-00' + footer)

        ax = figure().gca()
        ax.semilogx(dens['Total'],dens.index)
        ax.set_xlabel('Total Mass Density [kg m$^{-3}$]')
        ax.set_ylabel('altitude [km]')
        ax.grid(True)
        ax.set_title('Total Mass Density from MSISE-00'+footer)

        ax = figure().gca()
        ax.plot(temp['heretemp'],temp.index)
        ax.set_xlabel('Temperature')
        ax.set_ylabel('altitude [km]')
        ax.grid(True)
        ax.set_title('Temperature from MSISE-00' + footer)
    elif dens.ndim==4: #lat/lon grid
        if dtime.size>8:
            print('silently outputting plots to ' + rodir)
#%%sun lat/lon #FIXME this is a seemingly arbitrary procedure
        ttime = Time(dtime)
        obs = EarthLocation(0,0) # geodetic lat,lon = 0,0 arbitrary
        sun = get_sun(time=ttime)
        aaf = AltAz(obstime=ttime,location=obs)
        sloc = sun.transform_to(aaf)
        slat,slon = aer2geodetic(sloc.az.value, sloc.alt.value, sloc.distance.value,0,0,0)[:2]
#%%
        for k,t in enumerate(dens): #dens is a Panel4D
            fg,ax = subplots(4,2,sharex=True, figsize=(8,8))
            fg.suptitle(str(t) + ' at alt.(km) '+str(altkm) +
                        '\nAp='+str(ap[0]) + '  F10.7='+str(f107),
                         fontsize=14)
            ax=ax.ravel(); i = 0 #don't use enumerate b/c of skip
            for g in dens[t].items:
                if g != 'Total':
                    a = ax[i]
                    hi = a.imshow(dens.loc[t,g].values, aspect='auto',
                             extent=(glon[0,0],glon[0,-1],glat[0,0],glat[-1,0]))
                    fg.colorbar(hi,ax=a, format=sfmt)
                    a.plot(slon[k],slat[k],linestyle='none',
                                            marker='o',markersize=5,color='w')
                    a.set_title('Density: ' + g,fontsize=11)
                    a.set_xlim(-180,180)
                    a.set_ylim(-90,90)
                    a.autoscale(False)
                    i+=1
            for i in range(0,6+2,2):
                ax[i].set_ylabel('latitude (deg)')
            for i in (6,7):
                ax[i].set_xlabel('longitude (deg)')
            thisofn = rodir+'/{:.1f}_{:03d}'.format(altkm[0],k) + '.png'
            fg.savefig(thisofn,dpi=100,bbox_inches='tight')
            if dtime.size>8:
                print('wrote ' + thisofn)
                close()
    else:
        print('densities' + str(dens))
        print('temperatures ' + str(temp))

def latlonworldgrid(latstep=5,lonstep=5):
    lat = arange(-90,90+latstep,latstep)
    lon = arange(-180,180+lonstep,lonstep)
    glon,glat = meshgrid(lon,lat)
    return glat,glon

if __name__ == '__main__':
    from argparse import ArgumentParser
    p = ArgumentParser(description='calls MSISE-00 from Python, a basic demo')
    p.add_argument('simtime',help='yyyy-mm-ddTHH:MM:SSZ time of sim',type=str,nargs='?',default=None)
    p.add_argument('-a','--altkm',help='altitude (km) (start,stop,step)',type=float,nargs='+',default=[None])
    p.add_argument('-c','--latlon',help='geodetic latitude/longitude (deg)',type=float,nargs=2,default=(None,None))
    p.add_argument('--f107a',help=' 81 day AVERAGE OF F10.7 FLUX (centered on day DDD)',type=float,default=150)
    p.add_argument('--f107',help='DAILY F10.7 FLUX FOR PREVIOUS DAY',type=float,default=150)
    p.add_argument('--ap',help='daily ap, 0-3hr, 3-6hr, 6-9hr, 9-12hr,12-33hr, 36-57hr',type=float,nargs=7,default=[4,4,4,4,4,4,4])
    p.add_argument('--mass',help=('MASS NUMBER (ONLY DENSITY FOR SELECTED GAS IS ' +
                       'CALCULATED.  MASS 0 IS TEMPERATURE.  MASS 48 FOR ALL. '+
                         'MASS 17 IS Anomalous O ONLY.'),type=float,default=48)
    p = p.parse_args()

    if p.simtime is None: #cycle through a few times for a demo
        dtime = date_range(parse(''),periods=24,freq='1H',tz=UTC,normalize=True).to_pydatetime()
    else:
        dtime = parse(p.simtime)
    print('using simulation time(s): ' + str(dtime))
#%% altitude 1-D mode
    if p.latlon[0] and p.latlon[1]:
        print('entering single location mode, ',end='')
        if p.altkm[0] is None:
            amm = (60,1000,5)
        elif len(p.altkm) == 3:
            amm = p.altkm[0],p.altkm[1],p.altkm[2]
            if p.latlon[0] is None: #use pfisr coord
                glat = 65; glon=-148
        altkm = arange(amm[0],amm[1],amm[2])
        glat,glon=p.latlon
#%% lat/lon grid mode at constant altitude
    else:# len(p.altkm)==1:
        print('lat/lon not specified, entering auto whole-world grid mode at first altitude')
        if p.altkm[0] is None:
            altkm = 200
        else:
            altkm = p.altkm[0]
        glat,glon = latlonworldgrid()

    altkm = atleast_1d(altkm)
    print('using altitudes from {:.1f} to {:.1f} km'.format(altkm[0],altkm[-1]))

    dens,temp = testgtd7(dtime,altkm,glat,glon,p.f107a,p.f107,p.ap,p.mass)

    plotgtd(dens,temp,dtime,altkm,p.ap,p.f107,glat,glon)
    show()