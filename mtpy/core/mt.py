# -*- coding: utf-8 -*-
"""
.. module:: MT
   :synopsis: The main container for MT response functions.

.. moduleauthor:: Jared Peacock <jpeacock@usgs.gov>
"""

# ==============================================================================
import numpy as np
import os
import logging

from scipy import interpolate as spi

from mtpy.core import metadata
from mtpy.utils import gis_tools
import mtpy.core.z as MTz
import mtpy.analysis.pt as MTpt
import mtpy.analysis.distortion as MTdistortion
from mtpy.core.io.readwrite import read_file, write_file


# =============================================================================
class MT(object):
    """
    Basic MT container to hold all information necessary for a MT station
    including the following parameters.

    The most used attributes are made available from MT, namely the following.

    ===================== =====================================================
    Attribute             Description
    ===================== =====================================================
    station               station name
    latitude                   station latitude in decimal degrees
    longitude                   station longitude in decimal degrees
    elevation                  station elevation in meters
    Z                     mtpy.core.z.Z object for impedance tensor
    Tipper                mtpy.core.z.Tipper object for tipper
    pt                    mtpy.analysis.pt.PhaseTensor for phase tensor
    east                  station location in UTM coordinates assuming WGS-84
    north                 station location in UTM coordinates assuming WGS-84
    utm_zone              zone of UTM coordinates assuming WGS-84
    rotation_angle        rotation angle of the data
    fn                    absolute path to the data file
    ===================== =====================================================

    Other information is contained with in the different class attributes. For
    instance survey name is in MT.Site.survey

    .. note::

        * The best way to see what all the information is and where it is
          contained would be to write out a configuration file ::

              >>> import mtpy.core.mt as mt
              >>> mt_obj = mt.MT()
              >>> mt_obj.write_cfg_file(r"/home/mt/generic.cfg")

        * Currently EDI, XML, and j file are supported to read in information,
          and can write out EDI and XML formats.  Will be extending to j and
          Egberts Z format.

    ===================== =====================================================
    Methods               Description
    ===================== =====================================================
    read_mt_file          read in a MT file [ EDI | XML | j ]
    write_mt_file         write a MT file [ EDI | XML ]
    read_cfg_file         read a configuration file
    write_cfg_file        write a configuration file
    remove_distortion     remove distortion  following Bibby et al. [2005]
    remove_static_shift   Shifts apparent resistivity curves up or down
    interpolate           interpolates Z and T onto specified frequency array.
    ===================== =====================================================


    Examples
    -------------------
    :Read from an .edi File: ::

        >>> import mtpy.core.mt as mt
        >>> mt_obj = mt.MT(r"/home/edi_files/s01.edi")

    :Remove Distortion: ::

        >>> import mtpy.core.mt as mt
        >>> mt1 = mt.MT(fn=r"/home/mt/edi_files/mt01.edi")
        >>> D, new_z = mt1.remove_distortion()
        >>> mt1.write_mt_file(new_fn=r"/home/mt/edi_files/mt01_dr.edi",\
        >>>                    new_Z=new_z)

    :Remove Static Shift: ::

        >>> new_z_obj = mt_obj.remove_static_shift(ss_x=.78, ss_y=1.1)
        >>> # write a new edi file
        >>> mt_obj.write_mt_file(new_fn=r"/home/edi_files/s01_ss.edi",
        >>>                       new_Z=new_z)
        >>> wrote file to: /home/edi_files/s01_ss.edi

    :Interpolate: ::

        >>> new_freq = np.logspace(-3, 3, num=24)
        >>> new_z_obj, new_tipper_obj = mt_obj.interpolate(new_freq)
        >>> mt_obj.write_mt_file(new_Z=new_z_obj, new_Tipper=new_tipper_obj)
        >>> wrote file to: /home/edi_files/s01_RW.edi
    """

    def __init__(self, fn=None, **kwargs):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        self.survey_metadata = metadata.Survey()
        self.station_metadata = metadata.Station()
        self.station_metadata.run_list.append(metadata.Run())
        self.station_metadata.run_list[0].ex = metadata.Electric(component='ex')
        self.station_metadata.run_list[0].ey = metadata.Electric(component='ey')
        self.station_metadata.run_list[0].hx = metadata.Magnetic(component='hx')
        self.station_metadata.run_list[0].hy = metadata.Magnetic(component='hy')
        self.station_metadata.run_list[0].hz = metadata.Magnetic(component='hz')
        
        self._east = None
        self._north = None
        self._utm_zone = None

        self._Z = MTz.Z()
        self._Tipper = MTz.Tipper()
        self._rotation_angle = 0

        self.save_dir = os.getcwd()
        self.original_file_type = None
        if fn is not None:
            self.read_mt_file(fn)
            self._fn = os.path.normpath(os.path.abspath(fn))  # store file reference

        # provide key words to fill values if an edi file does not exist
        for key in list(kwargs.keys()):
            setattr(self, key, kwargs[key])
            
    def __str__(self):
        lines = [f"Station: {self.station}", '-' * 50]
        lines.append(f"\tSurvey:        {self.survey_metadata.survey_id}")
        lines.append(f"\tProject:       {self.survey_metadata.project}")
        lines.append(f"\tAcquired by:   {self.station_metadata.acquired_by.author}")
        lines.append(f"\tAcquired date: {self.station_metadata.time_period.start_date}")
        lines.append(f"\tLatitude:      {self.latitude:.3f}")
        lines.append(f"\tLongitude:     {self.longitude:.3f}")
        lines.append(f"\tElevation:     {self.elevation:.3f}")
        if self.Tipper.tipper is not None:
            lines.append("\tTipper:        True")
        else:
            lines.append("\tTipper:        False")
        
        if self.Z.z is not None:
            lines.append(f"\tPeriods: {len(self.Z.freq)}")
            lines.append(f"\t\tPeriod Range:   {1./self.Z.freq.max():.5E}  -- {1./self.Z.freq.min():.5E} s")
            lines.append(f"\t\tFrequency Range {self.Z.freq.min():.5E}  -- {self.Z.freq.max():.5E} s")
            
        return '\n'.join(lines)
    
    def __repr__(self):
        return self.__str__()

    # ==========================================================================
    # get functions
    # ==========================================================================
    @property
    def fn(self):
        """ reference to original data file"""
        return self._fn

    @property
    def latitude(self):
        """Latitude"""
        return self.station_metadata.location.latitude

    @property
    def longitude(self):
        """Longitude"""
        return self.station_metadata.location.longitude

    @property
    def elevation(self):
        """Elevation"""
        return self.station_metadata.location.elevation

    @property
    def east(self):
        """easting (m)"""
        return self._east

    @property
    def north(self):
        """northing (m)"""
        return self._north

    @property
    def utm_zone(self):
        """utm zone"""
        return self._utm_zone

    @property
    def rotation_angle(self):
        """rotation angle in degrees from north"""
        return self._rotation_angle

    @property
    def Z(self):
        """mtpy.core.z.Z object to hole impedance tensor"""
        return self._Z

    @property
    def Tipper(self):
        """mtpy.core.z.Tipper object to hold tipper information"""
        return self._Tipper

    @property
    def station(self):
        """station name"""
        return self.station_metadata.id

    @property
    def pt(self):
        """mtpy.analysis.pt.PhaseTensor object to hold phase tensor"""
        return MTpt.PhaseTensor(z_object=self.Z)

    @property
    def ex_metadata(self):
        """ EX metadata """
        return self.station_metadata.run_list[0].ex
    
    @property
    def ey_metadata(self):
        """ EY metadata """
        return self.station_metadata.run_list[0].ey
    
    @property
    def hx_metadata(self):
        """ HX metadata """
        return self.station_metadata.run_list[0].hx
    
    @property
    def hy_metadata(self):
        """ HY metadata """
        return self.station_metadata.run_list[0].hy
    
    @property
    def hz_metadata(self):
        """ HZ metadata """
        return self.station_metadata.run_list[0].hz
    
    @property
    def rrhx_metadata(self):
        """ RRHX metadata """
        return self.station_metadata.run_list[0].rrhx
    
    @property
    def rrhy_metadata(self):
        """ RRHY metadata """
        return self.station_metadata.run_list[0].rrhy
    
    # ==========================================================================
    # set functions
    # ==========================================================================
    @latitude.setter
    def latitude(self, latitude):
        """
        set latitude making sure the input is in decimal degrees

        upon setting utm coordinates are recalculated
        """
        self.station_metadata.location.latitude = latitude
        if self.longitude is not None or self.longitude != 0.0:
            self._east, self._north, self._utm_zone = gis_tools.project_point_ll2utm(
                self.latitude,
                self.longitude,
                datum=self.station_metadata.location.datum,
            )

    @longitude.setter
    def longitude(self, longitude):
        """
        set longitude making sure the input is in decimal degrees

        upon setting utm coordinates are recalculated
        """
        self.station_metadata.location.longitude = longitude
        if self.latitude is not None or self.latitude != 0.0:
            self._east, self._north, self._utm_zone = gis_tools.project_point_ll2utm(
                self.latitude,
                self.longitude,
                datum=self.station_metadata.location.datum,
            )

    @elevation.setter
    def elevation(self, elevation):
        """
        set elevation, should be input as meters
        """
        self.station_metadata.location.elevation = elevation

    @east.setter
    def east(self, easting):
        """
        set easting in meters

        upon setting latitude and longitude are recalculated
        """
        self._east = float(easting)
        if self.north is not None and self.utm_zone is not None:
            self.logger.debug("Calculating latitude and longitude from UTM")
            self._latitude, self._longitude = gis_tools.project_point_utm2ll(
                self.east, self.north, self.utm_zone
            )

    @north.setter
    def north(self, northing):
        """
        set northing in meters

        upon setting latitude and longitude are recalculated
        """
        self._north = float(northing)
        if self.east is not None and self.utm_zone is not None:
            self.logger.debug("Calculating latitude and longitude from UTM")
            self._latitude, self._longitude = gis_tools.project_point_utm2ll(
                self.east, self.north, self.utm_zone
            )

    @utm_zone.setter
    def utm_zone(self, utm_zone):
        """
        set UTM zone

        upon setting latitude and longitude are recalculated
        
        TODO: need a validation from utm zone
        """
        self._utm_zone = utm_zone
        if self.north is not None and self.east is not None:
            self.logger.debug("Calculating latitude and longitude from UTM")
            lat, lon= gis_tools.project_point_utm2ll(
                self.east, self.north, self.utm_zone
            )
            self.station_metadata.location.latitude = lat
            self.station_metadata.location.longitude = lon

    @rotation_angle.setter
    def rotation_angle(self, theta_r):
        """
        set rotation angle in degrees assuming North is 0 measuring clockwise
        positive to East as 90.

        upon setting rotates Z and Tipper
        """

        self._rotation_angle = theta_r
        self._Z.rotate(theta_r)
        self._Tipper.rotate(theta_r)
        self.pt.rotate(theta_r)

        print(
            (
                "Rotated Z, Tipper, Phase Tensor and Zinvariants by"
                "{0:.3f} degrees".format(self._rotation_angle)
            )
        )

    @Z.setter
    def Z(self, z_object):
        """
        set z_object

        recalculate phase tensor and invariants, which shouldn't change except
        for strike angle
        """

        self._Z = z_object
        self._Z.compute_resistivity_phase()

    @Tipper.setter
    def Tipper(self, t_object):
        """
        set tipper object

        recalculate tipper angle and magnitude
        """

        self._Tipper = t_object
        if self._Tipper is not None:
            self._Tipper.compute_amp_phase()
            self._Tipper.compute_mag_direction()

    @station.setter
    def station(self, station_name):
        """
        set station name
        """
        self.station_metadata.id = station_name
        
    @ex_metadata.setter
    def ex_metadata(self, value):
        """ set EX metadata """
        self.station_metadata.run_list[0].ex = value
            
    @ey_metadata.setter
    def ey_metadata(self, value):
        """ set EY metadata """
        self.station_metadata.run_list[0].ey = value
        
    @hx_metadata.setter
    def hx_metadata(self, value):
        """ set hx metadata """
        self.station_metadata.run_list[0].hx = value
        
    @hy_metadata.setter
    def hy_metadata(self, value):
        """ set hy metadata """
        self.station_metadata.run_list[0].hy = value
        
    @hz_metadata.setter
    def hz_metadata(self, value):
        """ set hz metadata """
        self.station_metadata.run_list[0].hz = value

    def remove_distortion(self, num_freq=None):
        """
        remove distortion following Bibby et al. [2005].

        :param num_freq: number of frequencies to look for distortion from the
                         highest frequency
        :type num_freq: int

        :returns: Distortion matrix
        :rtype: np.ndarray(2, 2, dtype=real)

        :returns: Z with distortion removed
        :rtype: mtpy.core.z.Z

        :Remove distortion and write new .edi file: ::

            >>> import mtpy.core.mt as mt
            >>> mt1 = mt.MT(fn=r"/home/mt/edi_files/mt01.edi")
            >>> D, new_z = mt1.remove_distortion()
            >>> mt1.write_mt_file(new_fn=r"/home/mt/edi_files/mt01_dr.edi",\
            >>>                    new_Z=new_z)

        """
        dummy_z_obj = MTz.copy.deepcopy(self.Z)
        D, new_z_object = MTdistortion.remove_distortion(
            z_object=dummy_z_obj, num_freq=num_freq
        )

        return D, new_z_object

    def remove_static_shift(self, ss_x=1.0, ss_y=1.0):
        """
        Remove static shift from the apparent resistivity

        Assume the original observed tensor Z is built by a static shift S
        and an unperturbated "correct" Z0 :

             * Z = S * Z0

        therefore the correct Z will be :
            * Z0 = S^(-1) * Z


        :param ss_x: correction factor for x component
        :type ss_x: float

        :param ss_y: correction factor for y component
        :type ss_y: float

        :returns: new Z object with static shift removed
        :rtype: mtpy.core.z.Z

        .. note:: The factors are in resistivity scale, so the
                  entries of  the matrix "S" need to be given by their
                  square-roots!

        :Remove Static Shift: ::

            >>> import mtpy.core.mt as mt
            >>> mt_obj = mt.MT(r"/home/mt/mt01.edi")
            >>> new_z_obj = mt.remove_static_shift(ss_x=.5, ss_y=1.2)
            >>> mt_obj.write_mt_file(new_fn=r"/home/mt/mt01_ss.edi",
            >>> ...                   new_Z_obj=new_z_obj)
        """

        s_array, new_z = self.Z.remove_ss(
            reduce_res_factor_x=ss_x, reduce_res_factor_y=ss_y
        )

        new_z_obj = MTz.Z(
            z_array=new_z, z_err_array=self.Z.z_err.copy(), freq=self.Z.freq.copy()
        )

        return new_z_obj

    def interpolate(
        self,
        new_freq_array,
        interp_type="slinear",
        bounds_error=True,
        period_buffer=None,
    ):
        """
        Interpolate the impedance tensor onto different frequencies

        :param new_freq_array: a 1-d array of frequencies to interpolate on
                               to.  Must be with in the bounds of the existing
                               frequency range, anything outside and an error
                               will occur.
        :type new_freq_array: np.ndarray
        :param period_buffer: maximum ratio of a data period and the closest
                              interpolation period. Any points outside this
                              ratio will be excluded from the interpolated
                              impedance array.

        :returns: a new impedance object with the corresponding
                               frequencies and components.
        :rtype: mtpy.core.z.Z

        :returns: a new tipper object with the corresponding
                                    frequencies and components.
        :rtype: mtpy.core.z.Tipper

        :Interpolate: ::

            >>> import mtpy.core.mt as mt
            >>> edi_fn = r"/home/edi_files/mt_01.edi"
            >>> mt_obj = mt.MT(edi_fn)
            >>> # create a new frequency range to interpolate onto
            >>> new_freq = np.logspace(-3, 3, 24)
            >>> new_z_object, new_tipper_obj = mt_obj.interpolate(new_freq)
            >>> mt_obj.write_mt_file(new_fn=r"/home/edi_files/mt_01_interp.edi",
            >>> ...                   new_Z_obj=new_z_object,
            >>> ...                   new_Tipper_obj=new_tipper_object)

        """

        # make sure the input is a numpy array
        if not isinstance(new_freq_array, np.ndarray):
            new_freq_array = np.array(new_freq_array)

        if period_buffer is not None:
            if 0.0 < period_buffer < 1.0:
                period_buffer += 1.0
                print("Warning: period buffer must be > 1. Updating to", period_buffer)

        # check the bounds of the new frequency array
        if bounds_error:
            # YG: the commented block below seems no longer necessary.
            # floater = 1.e-8  # FZ: a small offset to avoid out-of-bound error in spi interpolation module.
            # self._logger.info("massage the new_freq_array's min and max to avoid out-of-bound interp")
            # minindex = np.argmin(new_freq_array)
            # maxindex = np.argmax(new_freq_array)
            # new_freq_array[minindex] += floater
            # new_freq_array[maxindex] -= floater

            # logger.debug("new freq array %s", new_freq_array)
            if self.Z.freq.min() > new_freq_array.min():
                raise ValueError(
                    "New frequency minimum of {0:.5g}".format(new_freq_array.min())
                    + " is smaller than old frequency minimum of {0:.5g}".format(
                        self.Z.freq.min()
                    )
                    + ".  The new frequency range needs to be within the "
                    + "bounds of the old one."
                )
            if self.Z.freq.max() < new_freq_array.max():
                raise ValueError(
                    "New frequency maximum of {0:.5g}".format(new_freq_array.max())
                    + "is smaller than old frequency maximum of {0:.5g}".format(
                        self.Z.freq.max()
                    )
                    + ".  The new frequency range needs to be within the "
                    + "bounds of the old one."
                )

        # make a new Z object
        new_Z = MTz.Z(
            z_array=np.zeros((new_freq_array.shape[0], 2, 2), dtype="complex"),
            z_err_array=np.zeros((new_freq_array.shape[0], 2, 2)),
            freq=new_freq_array,
        )

        new_Tipper = MTz.Tipper(
            tipper_array=np.zeros((new_freq_array.shape[0], 1, 2), dtype="complex"),
            tipper_err_array=np.zeros((new_freq_array.shape[0], 1, 2)),
            freq=new_freq_array,
        )

        # interpolate the impedance tensor
        for ii in range(2):
            for jj in range(2):
                # need to look out for zeros in the impedance
                # get the indicies of non-zero components
                nz_index = np.nonzero(self.Z.z[:, ii, jj])

                if len(nz_index[0]) == 0:
                    continue
                # get the non-zero components
                z_real = self.Z.z[nz_index, ii, jj].real
                z_imag = self.Z.z[nz_index, ii, jj].imag
                z_err = self.Z.z_err[nz_index, ii, jj]

                # get the frequencies of non-zero components
                f = self.Z.freq[nz_index]

                # get frequencies to interpolate on to, making sure the
                # bounds are with in non-zero components
                new_nz_index = np.where(
                    (new_freq_array >= f.min()) & (new_freq_array <= f.max())
                )[0]
                new_f = new_freq_array[new_nz_index]

                # apply period buffer
                if type(period_buffer) in [float, int]:
                    new_f_update = []
                    new_nz_index_update = []
                    for ifidx, ifreq in enumerate(new_f):
                        # find nearest data period
                        difference = np.abs(np.log10(ifreq) - np.log10(f))
                        fidx = np.where(difference == np.amin(difference))[0][0]
                        if max(f[fidx] / ifreq, ifreq / f[fidx]) < period_buffer:
                            new_f_update.append(ifreq)
                            new_nz_index_update.append(new_nz_index[ifidx])
                    new_f = np.array(new_f_update)
                    new_nz_index = np.array(new_nz_index_update)

                # create a function that does 1d interpolation
                z_func_real = spi.interp1d(f, z_real, kind=interp_type)
                z_func_imag = spi.interp1d(f, z_imag, kind=interp_type)
                z_func_err = spi.interp1d(f, z_err, kind=interp_type)

                # interpolate onto new frequency range
                new_Z.z[new_nz_index, ii, jj] = z_func_real(new_f) + 1j * z_func_imag(
                    new_f
                )
                new_Z.z_err[new_nz_index, ii, jj] = z_func_err(new_f)

        # compute resistivity and phase for new Z object
        new_Z.compute_resistivity_phase()

        # if there is not tipper than skip
        if self.Tipper.tipper is None:
            return new_Z, new_Tipper

        # interpolate the Tipper
        for jj in range(2):
            # get indicies of non-zero components
            nz_index = np.nonzero(self.Tipper.tipper[:, 0, jj])

            if len(nz_index[0]) < 2:
                continue

            # get non-zero components
            t_real = self.Tipper.tipper[nz_index, 0, jj].real
            t_imag = self.Tipper.tipper[nz_index, 0, jj].imag
            t_err = self.Tipper.tipper_err[nz_index, 0, jj]

            # get frequencies for non-zero components
            f = self.Tipper.freq[nz_index]

            # create interpolation functions
            t_func_real = spi.interp1d(f, t_real, kind=interp_type)
            t_func_imag = spi.interp1d(f, t_imag, kind=interp_type)
            t_func_err = spi.interp1d(f, t_err, kind=interp_type)

            # get new frequency to interpolate over, making sure bounds are
            # for non-zero components
            new_nz_index = np.where(
                (new_freq_array >= f.min()) & (new_freq_array <= f.max())
            )
            new_f = new_freq_array[new_nz_index]

            # interpolate onto new frequency range
            new_Tipper.tipper[new_nz_index, 0, jj] = t_func_real(
                new_f
            ) + 1j * t_func_imag(new_f)

            new_Tipper.tipper_err[new_nz_index, 0, jj] = t_func_err(new_f)

        new_Tipper.compute_mag_direction()

        return new_Z, new_Tipper

    def plot_mt_response(self, **kwargs):
        """
        Returns a mtpy.imaging.plotresponse.PlotResponse object

        :Plot Response: ::

            >>> mt_obj = mt.MT(edi_file)
            >>> pr = mt.plot_mt_response()
            >>> # if you need more info on plot_mt_response
            >>> help(pr)

        """

        from mtpy.imaging import plot_mt_response

        # todo change this to the format of the new imaging API
        plot_obj = plot_mt_response.PlotMTResponse(
            z_object=self.Z,
            t_object=self.Tipper,
            pt_obj=self.pt,
            station=self.station,
            **kwargs
        )

        return plot_obj
        # raise NotImplementedError
        
    def write_mt_file(
            self,
            save_dir=None,
            fn_basename=None,
            file_type="edi",
            longitude_format="longitude",
            latlon_format="dms",
        ):
        """
        Write an mt file, the supported file types are EDI and XML.

        .. todo:: jtype and Gary Egberts z format

        :param save_dir: full path save directory
        :type save_dir: string

        :param fn_basename: name of file with or without extension
        :type fn_basename: string

        :param file_type: [ 'edi' | 'xml' ]
        :type file_type: string

        :param longitude_format:  whether to write longitude as longitude or LONG. 
                                  options are 'longitude' or 'LONG', default 'longitude'
        :type longitude_format:  string
        :param latlon_format:  format of latitude and longitude in output edi,
                               degrees minutes seconds ('dms') or decimal 
                               degrees ('dd')
        :type latlon_format:  string
        
        :returns: full path to file
        :rtype: string

        :Example: ::

            >>> mt_obj.write_mt_file(file_type='xml')

        """

        if save_dir is not None:
            self.save_dir = save_dir

        if fn_basename is not None:
            ext = os.path.splitext(fn_basename)[1][1:].lower()
            fn_basename = os.path.splitext(fn_basename)[0]
            if ext == "":
                fn_basename = "{0}.{1}".format(fn_basename, file_type.lower())
            elif ext in ["xml", "edi"]:
                fn_basename = "{0}.{1}".format(fn_basename, ext)
                file_type = ext
            else:
                raise MTError("File type {0} not supported yet.".format(ext))
        else:
            fn_basename = "{0}.{1}".format(self.station, file_type)

        fn = os.path.join(self.save_dir, fn_basename)

        return write_file(self, fn, file_type=file_type)
        
def read_mt_file(fn, file_type=None):
    """
    
    Read an MT response file.

    .. note:: Currently only .edi, .xml, and .j files are supported

    :param fn: full path to input file
    :type fn: string

    :param file_type: ['edi' | 'j' | 'xml' | ... ]
                      if None, automatically detects file type by
                      the extension.
    :type file_type: string

    :Example: ::

        >>> import mtpy.core.mt as mt
        >>> mt_obj = mt.MT()
        >>> mt_obj.read_mt_file(r"/home/mt/mt01.xml")
    
    :param fn: DESCRIPTION
    :type fn: TYPE
    :return: DESCRIPTION
    :rtype: TYPE

    """
    
    return read_file(fn, file_type=file_type)
        


# ==============================================================================
#             Error
# ==============================================================================


class MTError(Exception):
    pass
