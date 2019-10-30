#! /usr/bin/env python
"""
Description:
    Convert input MODEM data  and resistivity rho files into a georeferenced raster/grid format,
    such as geotiff format, which can be visualized by GIS software.

CreationDate:   1/05/2019
Developer:      fei.zhang@ga.gov.au

Revision History:
    LastUpdate:     1/05/2019   FZ
    LastUpdate:     17/09/2019  FZ fix the geoimage coordinates, upside-down issues 
    LastUpdate:     dd/mm/yyyy
"""

import os,sys
import argparse
from pyproj import Proj
import gdal, osr
import numpy as np
from mtpy.modeling.modem import Model, Data
from mtpy.utils import gis_tools
from mtpy.contrib.netcdf import nc
import mtpy.contrib.netcdf.modem_to_netCDF as modem2nc


def array2geotiff_writer(newRasterfn, rasterOrigin, pixelWidth, pixelHeight, array, epsg_code=4283):

    cols = array.shape[1]
    rows = array.shape[0]
    originX = rasterOrigin[0]
    originY = rasterOrigin[1]

    driver = gdal.GetDriverByName('GTiff')
    # driver = gdal.GetDriverByName('AAIGrid')
    outRaster = driver.Create(newRasterfn, cols, rows, 1, gdal.GDT_Float32)
    outRaster.SetGeoTransform((originX, pixelWidth, 0, originY, 0, pixelHeight))
    outband = outRaster.GetRasterBand(1)
    outband.WriteArray(array)
    outRasterSRS = osr.SpatialReference()
    outRasterSRS.ImportFromEPSG(epsg_code)
    outRaster.SetProjection(outRasterSRS.ExportToWkt())
    outband.FlushCache()

# output to ascii format
    format2 = 'AAIGrid'
    newRasterfn2 = "%s.asc"%newRasterfn
    driver2 = gdal.GetDriverByName(format2)
    dst_ds_new = driver2.CreateCopy(newRasterfn2, outRaster)


    return newRasterfn


def test_array2geotiff(newRasterfn, epsg):
    #rasterOrigin = (-123.25745,45.43013)
    rasterOrigin = (149.298, -34.974)  # Longitude and Lattitude in Aussi continent
    pixelWidth = 0.01
    pixelHeight = -0.01  # this must be negative value, as a Geotiff image's origin is defined as the upper-left corner.

    # Define an image 2D-array: The black=0 pixels trace out GDAL; the bright=1 pixels are white background
    array = np.array([[ 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
                      [ 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
                      [ 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 1],
                      [ 1, 0, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1, 1],
                      [ 1, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 1, 1],
                      [ 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1, 1],
                      [ 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 1, 0, 0, 0, 1],
                      [ 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
                      [ 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
                      [ 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]])


    random= np.random.rand(array.shape[0],array.shape[1])

    array2= 1000.0*array + 10.0*random
    print (array2)

    outfn=array2geotiff_writer(newRasterfn, rasterOrigin, pixelWidth, pixelHeight, array2, epsg_code=epsg)  # write to a raster file

    return outfn

def modem2geotiff(data_file, model_file, output_file, source_proj=None):
    """
    Generate an output geotiff file from a modems.dat file and related modems.rho model file
    :param data_file: modem.dat
    :param model_file: modem.rho
    :param output_file: output.tif
    :param source_proj: None by defult. The UTM zone infered from the input non-uniform grid parameters
    :return:
    """
    # Define Data and Model Paths
    data = Data()
    data.read_data_file(data_fn=data_file)

    # create a model object using the data object and read in model data
    model = Model(data_obj=data)
    model.read_model_file(model_fn=model_file)

    center = data.center_point
    if source_proj is None:
        zone_number, is_northern, utm_zone = gis_tools.get_utm_zone(center.lat.item(), center.lon.item())
        #source_proj = Proj('+proj=utm +zone=%d +%s +datum=%s' % (zone_number, 'north' if is_northern else 'south', 'WGS84'))

        epsg_code = gis_tools.get_epsg(center.lat.item(), center.lon.item())
        print("Input data epsg code is inferred as ", epsg_code)
    else:
        epsg_code = source_proj  # integer

    source_proj = Proj(init='epsg:' + str(epsg_code))

    resistivity_data = {
        'x': center.east.item() + (model.grid_east[1:] + model.grid_east[:-1])/2,
        'y': center.north.item() + (model.grid_north[1:] + model.grid_north[:-1])/2,
        'z': (model.grid_z[1:] + model.grid_z[:-1])/2,
        'resistivity': np.transpose(model.res_model, axes=(2, 0, 1))
    }

    #epsgcode= 4326 # 4326 output grid Coordinate systems: 4326 WGS84
    epsgcode= 4283  # 4283 https://spatialreference.org/ref/epsg/gda94/
    grid_proj = Proj(init='epsg:%s'%epsgcode) # output grid Coordinate system 
    # grid_proj = Proj(init='epsg:3112') # output grid Coordinate system 4326, 4283, 3112
    result = modem2nc.interpolate(resistivity_data, source_proj, grid_proj, center,
                         modem2nc.median_spacing(model.grid_east), modem2nc.median_spacing(model.grid_north))


    print("result['latitude'] ==", result['latitude'])
    print("result['longitude'] ==", result['longitude'])
    print("result['depth'] ==", result['depth'])

    #origin=(result['longitude'][0],result['latitude'][0]) # which corner of the image?
    origin=(result['longitude'][0],result['latitude'][-1])
    pixel_width = result['longitude'][1] - result['longitude'][0]
    pixel_height = result['latitude'][0] - result['latitude'][1] # This should be negative for geotiff with origin at the upper-left corner

    # write the depth_index
    depth_index=1
    resis_data = result['resistivity'][depth_index,:,:] # this original image may start from the lower left corner, if so must be flipped.
    resis_data_flip = resis_data[::-1]  # flipped to ensure the image starts from the upper left corner 

    array2geotiff_writer(output_file,origin,pixel_width,pixel_height,resis_data_flip, epsg_code=epsgcode)

    return output_file


def modem2geogrid_ak(data_file, model_file, output_file, source_proj=None, depth_index=None):
    """
    Generate an output geotiff file from a modems.dat file and related modems.rho model file
    :param data_file: modem.dat
    :param model_file: modem.rho
    :param output_file: output.tif
    :param source_proj: None by default. The UTM zone inferred from the input non-uniform grid parameters
    :return:
    """
    # Define Data and Model Paths
    data = Data()
    data.read_data_file(data_fn=data_file)

    # create a model object using the data object and read in model data
    model = Model(data_obj=data)
    model.read_model_file(model_fn=model_file)

    print("read inputs")

    #source_proj = 28355
    center = data.center_point
    if source_proj is None:
        zone_number, is_northern, utm_zone = gis_tools.get_utm_zone(center.lat.item(), center.lon.item())
        # source_proj = Proj('+proj=utm +zone=%d +%s +datum=%s' % (zone_number, 'north' if is_northern else 'south', 'WGS84'))

        epsg_code = gis_tools.get_epsg(center.lat.item(), center.lon.item())
        print("Input data epsg code is inferred as ", epsg_code)
    else:
        epsg_code = source_proj  # integer

    source_proj = Proj(init='epsg:' + str(epsg_code))

    resistivity_data = {
        'x': center.east.item() + (model.grid_east[1:] + model.grid_east[:-1]) / 2,
        'y': center.north.item() + (model.grid_north[1:] + model.grid_north[:-1]) / 2,
        'z': (model.grid_z[1:] + model.grid_z[:-1]) / 2,
        'resistivity': np.transpose(model.res_model, axes=(2, 0, 1))
    }

    #    resistivity_data = {
    #        'x': center.east.item() + (model.grid_east[7:-6] + model.grid_east[6:-7])/2,
    #        'y': center.north.item() + (model.grid_north[7:-6] + model.grid_north[6:-7])/2,
    #        'z': (model.grid_z[1:] + model.grid_z[:-1])/2,
    #        'resistivity': np.transpose(model.res_model[6:-6,6:-6], axes=(2, 0, 1))
    #    }

    print(resistivity_data['x'], resistivity_data['y'])

    print("got cell centres")
    print(resistivity_data['x'].shape, resistivity_data['y'].shape, resistivity_data['resistivity'].shape)

    # epsgcode= 4326 # 4326 output grid Coordinate systems: 4326 WGS84
    # epsgcode = 28355  # 4283 https://spatialreference.org/ref/epsg/gda94/
    grid_proj = source_proj  # output grid Coordinate system should be the same as the input modem's
    # grid_proj = Proj(init='epsg:3112') # output grid Coordinate system 4326, 4283, 3112
    result = modem2nc.interpolate(resistivity_data, source_proj, grid_proj, center,
                                  modem2nc.median_spacing(model.grid_east), modem2nc.median_spacing(model.grid_north))

    #    print("result['latitude'] ==", result['latitude'])
    #    print("result['longitude'] ==", result['longitude'])
    #    print("result['depth'] ==", result['depth'])

    # origin=(result['longitude'][0],result['latitude'][0]) # which corner of the image?
    origin = (result['longitude'][0], result['latitude'][-1])
    pixel_width = result['longitude'][1] - result['longitude'][0]
    pixel_height = result['latitude'][0] - result['latitude'][
        1]  # This should be negative for geotiff with origin at the upper-left corner

    # write the depth_index
    #    if depth_index is None:
    #        depth_indices = [1]
    #    else:
    depth_indices = range(len(resistivity_data['z']))
    print(depth_indices)

    #for depth_index in depth_indices:
    for depth_index in [0,1,2,3]:
        output_file = 'DepthSlice%1im' % (resistivity_data['z'][depth_index])
        resis_data = result['resistivity'][depth_index, :, :]

        # this original image may start from the lower left corner, if so must be flipped.
        resis_data_flip = resis_data[::-1]  # flipped to ensure the image starts from the upper left corner
        print(resis_data_flip)
        array2geotiff_writer(output_file, origin, pixel_width, pixel_height, resis_data_flip, epsg_code=epsg_code)

    return output_file


#####################################################################################################################
# Section for quick test run of this script
# cd /e/Githubz/mtpy
# Default output grid Coordinate systems:'epsg:4283' https://spatialreference.org/ref/epsg/gda94/
# (not the Old 4326 WGS84)
# export PYTHONPATH=/g/data/ha3/fxz547/Githubz/mtpy
# python mtpy/utils/convert_modem_data_to_geogrid.py examples/model_files/ModEM_2/Modular_MPI_NLCG_004.dat examples/model_files/ModEM_2/Modular_MPI_NLCG_004.rho
# python mtpy/utils/convert_modem_data_to_geogrid.py --output-file EF_NLCG_001_4283.tif tmp/JinMing_GridData_sample/EFTF_MT_model/EF_NLCG_001.dat  tmp/JinMing_GridData_sample/EFTF_MT_model/EF_NLCG_001.rho
#####################################################################################################################
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('modem_data', help="ModEM data file")
    parser.add_argument('modem_model', help="ModEM model file")
    parser.add_argument('--epsg', default=4283, help="EPSG code for the output CRS", type=int)
    parser.add_argument('--output-file', default="output.tif", help="Name of output file")

    args = parser.parse_args()

    print (args)

    ##test_array2geotiff("test_geotiff_GDAL_img.tif", args.epsg)

    #modem2geotiff(args.modem_data, args.modem_model, args.output_file)
    modem2geogrid_ak(args.modem_data, args.modem_model, args.output_file)


