'''
Calculates LSF, instrument background and transmission

CHANGELOG:

Version 0.0.0 (2023-10-27)
--------------------------
- Original HARMONI simulator code
Developers: Miguel Pereira Santaella, Laurence Routledge, Simon Zieleniewsk, Sarah Kendrew

Version 1.0.0 (2024-01-10)
--------------------------
- Changed the telescope area to be that of the telescope, not zero. (This was an issue from the HARMONI git!)
- Added logging info for troubleshooting.
- Changed logging info to use MAVIS rather than HARMONI.
- Updated FPRS and cryo temperature parameters to use MAVIS prefix.
- Removed MCI section of code.
Author: Eric Muller (eric.muller@anu.edu.au)

'''
import logging

import numpy as np
from scipy.interpolate import interp1d, interp2d
import scipy.constants as sp
from astropy.convolution import Gaussian1DKernel
from astropy.io import fits

from src.config import *
from src.modules.misc_utils import path_setup
from src.modules.em_model import *


tppath = path_setup('../../' + config_data["data_dir"] + 'throughput/')
hc_path = path_setup('../../' + config_data["data_dir"] + 'HC/')
AreaTel = config_data['telescope']['area'] # CHANGELOG 09-01-2024: changed this to the actual value, not zero (as it was in HSIM for some reason)

class InstrumentPart:
    substrate = "Suprasil3001_50mm_Emissivity.txt" # TODO: update these to the correct substrates. Note sure what the lenses should be and don't know where I can find the VLT emissivity curves
    mirror = "QuantumFS500_Emissivity.txt"
    edust = 0.5 # Grey Dust covering on some optics
    mindustfrac = 0.005 # 0.5% dust on optical surfaces - won't be perfectly clean

    def __init__(self, name, temp, area, n_mirrors=0, n_lenses=0, dust_lens=0., dust_mirror=mindustfrac, global_scaling=1., emis_scaling=1., emis_mirror=mirror, emis_lens=substrate, emis_dust=edust):
        if dust_lens != 0:
            assert(n_lenses != 0)
        
        self.name = name
        self.temp = temp
        self.area = area
        self.n_mirrors = n_mirrors
        self.n_lenses = n_lenses
        self.dust_lens = dust_lens
        self.dust_mirror = dust_mirror
        self.global_scaling = global_scaling
        self.emis_scaling = emis_scaling
        self.emis_mirror = emis_mirror
        self.emis_lens = emis_lens
        self.emis_dust = emis_dust
        self.number = 0

    def set_number(self, number):
        self.number = number

    def calcEmissivity(self, lamb, filename, scaling, dust, n):
        if n == 0:
            # Handles the case where there are mirrors but lens emissivity is being calculated, vice versa
            return 0.
        
        # Read emissivity from file or use "filename" as a number
        if type(filename) == str:
            l, emi = np.loadtxt(os.path.join(tppath, filename), unpack=True, comments="#", delimiter=",")
        else:
            l = lamb
            emi = np.zeros_like(lamb) + filename
            logging.info('Using constant emissivity %s for %s', filename, self.name) # CHANGELOG 09-01-2024: added for my troubleshooting, retaining as info?

        # logging.info('For %s - l: %s, emi: %s', self.name, l, emi) # CHANGELOG 09-01-2024: added for my troubleshooting
        
        # Scale emissivity
        emi *= scaling
        # Add dust emissivity
        emi += self.emis_dust*dust
        # Calculate emissivity for n elements
        emi = 1. - (1. - emi)**n # ~= n*emi for small emi
        # Scale depending on the effective area
        emi = emi*self.area/AreaTel
        # Interpolate emissivity to output lambda grid
        emi_interp = interp1d(l, emi, kind='linear', bounds_error=False, fill_value=0.)
        
        return emi_interp(lamb)

    def calcThroughputAndEmission(self, lamb, DIT, output_file=""):
        
        # mirrors
        emi_mirror = self.global_scaling*self.calcEmissivity(lamb, self.emis_mirror, self.emis_scaling, self.dust_mirror, self.n_mirrors)
        # lenses
        emi_lens = self.global_scaling*self.calcEmissivity(lamb, self.emis_lens, self.emis_scaling, self.dust_lens, self.n_lenses)
                
        emissivity = 1. - ((1. - emi_mirror)*(1. - emi_lens))
        throughput = 1. - emissivity
        emission = emissivity*blackbody(lamb, self.temp) #J/s/m2/lambda(um)/arcsec2
        
        emission_ph = emission/(sp.h*sp.c/(lamb*1.E-6))*DIT # photons/um/m2/arcsec2
        

        logging.debug("Instrument Part Model - {:02d} {}".format(self.number, self.name))
        logging.debug("T = {:d} K Mirrors = {:d} Lenses = {:d} Area = {:d} m2".format(*map(int, [self.temp, self.n_mirrors, self.n_lenses, self.area])))
        logging.debug("global_scaling = {:5.3f} emis_scaling = {:3.1f}".format(self.global_scaling, self.emis_scaling))
        logging.debug("emis_dust = %s", self.emis_dust)
            
        if self.n_mirrors > 0:
            logging.debug("emis_mirror = {} dust_mirror = {:5.3f}".format(self.emis_mirror, self.dust_mirror))
                
        if self.n_lenses > 0:
            logging.debug("emis_lens = {} dust_lens = {:5.3f}".format(self.emis_lens, self.dust_lens))
            
        logging.debug("lambda = {:7.4f} emissivity = {:6.3f} throughput = {:6.3f} emission_ph = {:.2e}".format(np.median(lamb), np.median(emissivity), np.median(throughput), np.median(emission_ph)))
        logging.debug("-------")
        
        if output_file is not None:
            plot_file = output_file + "_HARMONI_" + "{:02d}".format(self.number) + "_" + self.name.replace(" ", "_").lower()
                
            plt.clf()
            plt.plot(lamb, throughput)
            plt.xlabel(r"wavelength [$\mu$m]")
            plt.ylabel("Throughput " + self.name)
            plt.savefig(plot_file + "_tr.pdf")
            np.savetxt(plot_file + "_tr.txt", np.c_[lamb, throughput])

            plt.clf()
            plt.plot(lamb, emission_ph, label="Blackbody T = {:.1f} K".format(self.temp))
            plt.legend()
            plt.xlabel(r"wavelength [$\mu$m]")
            plt.ylabel("Emissivity " + self.name)
            plt.savefig(plot_file + "_em.pdf")
            np.savetxt(plot_file + "_em.txt", np.c_[lamb, emission_ph])
            
        
        return throughput, emission_ph
    
class Instrument:
    def __init__(self, name):
        self.name = name
        self.parts = []

    def addPart(self, part):
        self.parts.append(part)
        part.set_number(len(self.parts))

    def calcThroughputAndEmission(self, lamb, DIT, output_file=""):
        throughput = np.ones_like(lamb)
        emission = np.zeros_like(lamb)
    
        # CHANGELOG: Print the input list of parts for troubleshooting
        # logging.info("parts: %s", str([part.name for part in self.parts]))

        for part in self.parts:
            part_t, part_emi = part.calcThroughputAndEmission(lamb, DIT, output_file=output_file)
            
            # logging.info("part_t: %s, part_emi: %s", part_t, part_emi) # CHANGELOG 09-01-2024: added for my troubleshooting
  
            throughput *= part_t
            emission *= part_t
            emission = emission + part_emi

        # logging.info("throughput: %s", throughput) # CHANGELOG 09-01-2024: added for my troubleshooting
  
        # if output_file is not None:
            # logging.info("Total HARMONI backround: lambda = {:7.4f}, throughput = {:6.3f}, emission = {:.2e} ph/um/m2/arcsec2/s".format(np.median(lamb), np.median(throughput), np.median(emission)/DIT))
        # CHANGELOG 09-01-2024: Commented out the above, just print it regardless
        logging.info("Total MAVIS backround: lambda = {:7.4f}, throughput = {:6.3f}, emission = {:.2e} ph/um/m2/arcsec2/s".format(np.median(lamb), np.median(throughput), np.median(emission)/DIT)) # CHANGELOG 10-01-2024: Changed text from HARMONI to MAVIS


        return throughput, emission



def sim_instrument(input_parameters, cube, back_emission, transmission, ext_lambs, cube_lamb_mask, input_spec_res, debug_plots=False, output_file=""):
    ''' Simulates instrument effects
    Inputs:
        input_parameters: input dictionary
            exposure_time: Exposure time [s]
            grating: Spectral grating
            ao_mode: LTAO/SCAO/NOAO/AIRY/User defined PSF fits file
            telescope_temp: Telescope temperature [K]

        cube: Input datacube (RA, DEC, lambda)
        back_emission: Input background emission
        transmission: Input transmission
        ext_lambs: extended lambda array [um]
        cube_lamb_mask: mask array to get the lambs of the cube
        input_spec_res: Spectral resolution of the input cube [micron]
        debug_plots: Produce debug plots
        output_file: File name for debug plots

    Outputs:
        cube: cube including instrument effects
        back_emission: back_emission including telescope
        LSF_size: width of the LSF [A]
    '''
    
    # Get instrument transmission
    logging.info("Calculating MAVIS transmission and background") # CHANGELOG 10-01-2024: Changed text from HARMONI to MAVIS
    
    # CHANGELOG 11-01-2024: Changed to the MAVIS instrument
    mavis = Instrument("MAVIS")
    
    # Instrument model variables
    # -------------------------
    # Instrument temperatures
    TTel = input_parameters["telescope_temp"]
    #TCool = TTel - config_data['MAVIS_FPRS_diff_temp']
    TCool = 273.15 + config_data['MAVIS_FPRS_temp'] # fixed FPRS temp # CHANGELOG 29-12-2023: Changed to MAVIS prefix
    TCryo = config_data['MAVIS_cryo_temp'] # CHANGELOG 29-12-2023: Changed to MAVIS prefix
    TCryoMech = TCryo
    TTrap = TCool
    Touter_window = TTel - 0.2*(TTel - TCool)
    Tinner_window = TCool + 0.2*(TTel - TCool)
    AreaIns = (config_data['telescope']['diameter']*0.5)**2*np.pi    # Full 37m2 aperture, including central obstruction -- this what we see from a thermal point of view after cold stop
    AreaTel = config_data['telescope']['area']            # 37m with 11m central obscuration -- this is what we see before the cold stop

    # Dust properties
    dustfrac = 0.01
    dustfrac = max(InstrumentPart.mindustfrac, dustfrac)    # Can make outer surfaces more dusty to represent aging

    # Cold trap properties
    ecoldtrap = 1.
    rwindow = 0.01    # 1% AR coating on each surface
    # -------------------------
    
    logging.debug("MAVIS model. TCool = {:d} K TCryo = {:d} K TCryoMech = {:d} K TTrap  = {:d} K Touter_window = {:d} K Tinner_window = {:d} K".format(*map(int, [TCool, TCryo, TCryoMech, TTrap, Touter_window, Tinner_window])))
    logging.debug("AreaIns = {:6.1f} m2 AreaTel = {:6.1f} m2".format(AreaIns, AreaTel))
    logging.debug("edust = {:6.3f} dustfrac = {:6.3f} mindustfrac = {:6.3f}".format(InstrumentPart.edust, dustfrac, InstrumentPart.mindustfrac))
    logging.debug("ecoldtrap = {:6.3f} rwindow = {:6.3f}".format(ecoldtrap, rwindow))
    logging.debug("-------")
    
    
 
    #TODO: edit this to be the parts of MAVIS.
    # AO dichroic if present
    aoMode = input_parameters["ao_mode"]
    if aoMode == "LTAO":
        mavis.addPart(InstrumentPart("LTAO dichroic", TTel, AreaIns, n_lenses=1, emis_lens="LTAO_0.6_dichroic.txt", dust_lens=2.*dustfrac))
        mavis.addPart(InstrumentPart("AO cold trap", TTrap, AreaIns, n_mirrors=1, emis_mirror=0., dust_mirror=0.03, emis_dust=ecoldtrap))
    
    mavis.addPart(InstrumentPart("Outer window", Touter_window, AreaIns, n_lenses=1, emis_scaling=0.5, dust_lens=dustfrac + InstrumentPart.mindustfrac))
    mavis.addPart(InstrumentPart("Inner window", Tinner_window, AreaIns, n_lenses=1, emis_scaling=0.5, dust_lens=2.*InstrumentPart.mindustfrac))

    mavis.addPart(InstrumentPart("Window reflected", TTrap, AreaIns, n_mirrors=1, emis_mirror=0., dust_mirror=2.*0.8*2.0*rwindow, emis_dust=ecoldtrap))

    low_dust_iso6 = 1
    # FPRS
    if low_dust_iso6:
        mavis.addPart(InstrumentPart("FPRS", TCool, AreaTel, n_mirrors=4))
    else:
        mavis.addPart(InstrumentPart("FPRS", TCool, AreaTel, n_mirrors=3, dust_mirror=0.032))
        mavis.addPart(InstrumentPart("FPRS", TCool, AreaTel, n_mirrors=1, dust_mirror=0.008))
    
    if aoMode in ["SCAO", "HCAO"]:
        mavis.addPart(InstrumentPart("SCAO dichroic", TCool, AreaIns, n_lenses=1, emis_lens="SCAO_0.8_dichroic.txt", dust_lens=2.*dustfrac))
    
    if low_dust_iso6:
        mavis.addPart(InstrumentPart("Cryo window", TCool, AreaTel, n_lenses=1, emis_scaling=0.4, dust_lens=InstrumentPart.mindustfrac))
    else:
        mavis.addPart(InstrumentPart("Cryo window", TCool, AreaTel, n_lenses=1, emis_scaling=0.4, dust_lens=0.125))
        
    mavis.addPart(InstrumentPart("Cryo window inner dust", TCryo+50., AreaIns, n_mirrors=1, emis_mirror=0., dust_mirror=InstrumentPart.mindustfrac))
    mavis.addPart(InstrumentPart("Cryo window cold trap", TCryo+50., AreaIns, n_mirrors=1, emis_mirror=0., dust_mirror=2.0*rwindow, emis_dust=ecoldtrap))

    # Cryostat
    mavis.addPart(InstrumentPart("Pre-optics+IFU+Spectrograph", TCryoMech, AreaIns, n_lenses=11, n_mirrors=23))

    # Grating
    grating = input_parameters["grating"]
    mavis.addPart(InstrumentPart("Grating " + grating, TCryoMech, AreaIns, n_mirrors=1, emis_mirror=grating + "_grating.txt", dust_mirror=0))
    
    ################################ MAVIS frameworking ################################
    
    # Nasmyth flange -- spectrograph arms
    
 
 
    MAVIS_transmission, MAVIS_background = mavis.calcThroughputAndEmission(ext_lambs, input_parameters["exposure_time"], output_file=output_file)
    
    # CHANGELOG 08-01-2023: Commented this section out
    # if input_parameters["mci"]:
    #     logging.info("Using minimum compliant instrument background and throughput")
        
    #     bandws = config_data['gratings'][grating]
    #     mci_lamb = np.arange(bandws.lmin, bandws.lmax, (bandws.lmax+bandws.lmin)*0.5/bandws.R)
    #     mci_HARMONI_transmission, _ = harmoni.calcThroughputAndEmission(mci_lamb, input_parameters["exposure_time"], output_file=None)
        
    #     scaling_transmission = 1./np.mean(mci_HARMONI_transmission)*0.26
    #     HARMONI_transmission = np.interp(ext_lambs, mci_lamb, mci_HARMONI_transmission*scaling_transmission)
        
    #     #scaling_background = 2.031e3/(np.median(HARMONI_background)/input_parameters["exposure_time"])*np.median(HARMONI_transmission)/0.289
    #     scaling_background = 1.0754 # scaled background to match specifictaion at 2.2um at 9C
    #     HARMONI_background = scaling_background*HARMONI_background
        

    #     logging.info("Total MCI HARMONI backround: lambda = {:7.4f} throughput = {:6.3f} emission = {:.3e} ph/um/m2/arcsec2/s".format(np.median(ext_lambs), np.median(HARMONI_transmission), np.median(HARMONI_background)/input_parameters["exposure_time"]))

    #     plot_file = output_file + "_HARMONI_mci"
        
    #     plt.clf()
    #     plt.plot(ext_lambs, HARMONI_transmission)
    #     plt.xlabel(r"wavelength [$\mu$m]")
    #     plt.ylabel("Throughput mci")
    #     plt.savefig(plot_file + "_tr.pdf")
    #     np.savetxt(plot_file + "_tr.txt", np.c_[ext_lambs, HARMONI_transmission])

    #     plt.clf()
    #     plt.plot(ext_lambs, HARMONI_background, label="HARMONI mci")
    #     plt.legend()
    #     plt.xlabel(r"wavelength [$\mu$m]")
    #     plt.ylabel("Emissivity mci")
    #     plt.savefig(plot_file + "_em.pdf")
    #     np.savetxt(plot_file + "_em.txt", np.c_[ext_lambs, HARMONI_background])


    back_emission = back_emission*MAVIS_transmission
    transmission = transmission*MAVIS_transmission
    back_emission = back_emission + MAVIS_background
    
    # Add instrument emission/transmission to the input cube
    
    instrument_tr_cube = MAVIS_transmission[cube_lamb_mask]
    instrument_tr_cube.shape = (np.sum(cube_lamb_mask), 1, 1)
    cube *= instrument_tr_cube

    instrument_background_cube = MAVIS_background[cube_lamb_mask]
    instrument_background_cube.shape = (np.sum(cube_lamb_mask), 1, 1)
    cube += instrument_background_cube


    # - LSF
    logging.info("Convolve with LSF")
    # Assume Gaussian LSF
    bandws = config_data['gratings'][grating] # CHANGELOG 11-01-2024: Removed mci option
        
    new_res = (bandws.lmin + bandws.lmax)/(2.*bandws.R) # micron
    pix_size = (ext_lambs[1] - ext_lambs[0])
    if new_res > input_spec_res:
        new_res_pix = (new_res**2 - input_spec_res**2)**0.5/pix_size
    else:
        logging.warning("The output spectral resolution is higher than the input cube resolution. Assuming input resolution = 0 AA")
        new_res_pix = new_res/pix_size
        
    logging.info("Output resolution: {:.3f} AA".format(new_res*10000.))
    logging.info("Input resolution: {:.3f} AA".format(input_spec_res*10000.))
    logging.info("Effective LSF FWHM = {:.3f} AA".format(new_res_pix*pix_size*10000.))
    
    LSF_size = 0
    if new_res_pix > 1.: # avoid convolution with a kernel narrower than 1 pixel
        sigma_LSF_pix = new_res_pix/2.35482
    
        npix_LSF = int(sigma_LSF_pix*config_data['LSF_kernel_size'])
        # Ensure that the kernel has an odd number of channels
        if npix_LSF % 2 == 0:
            npix_LSF = npix_LSF + 1
            
        kernel_LSF = Gaussian1DKernel(stddev=sigma_LSF_pix, x_size=npix_LSF)
        z, y, x = cube.shape
        
        for py in range(y):
            for px in range(x):
                spectrum = np.copy(back_emission)
                spectrum[cube_lamb_mask] = cube[:, py, px]
                
                cube[:, py, px] = np.convolve(spectrum, kernel_LSF, mode="same")[cube_lamb_mask]
        
        
        back_emission = np.convolve(back_emission, kernel_LSF, mode="same")
        transmission = np.convolve(transmission, kernel_LSF, mode="same")
        
        LSF_size = npix_LSF*(ext_lambs[1] - ext_lambs[0])*10000. # AA
        logging.info("Range for the LSF convolution: {:.3f} AA".format(LSF_size))
    else:
        logging.warning("LSF convolution not performed because the effective LSF FWHM is < 1 pix")


    # Apply high-constrast focal plane mask
    if aoMode == "HCAO":
        logging.info("Apply HC focal plane mask " + input_parameters["hc_fp_mask"])
        fpm = fits.getdata(os.path.join(hc_path, input_parameters["hc_fp_mask"] + ".fits.gz"), 0, memmap=True) # 0.39 mas sampling
        fpm_sampling = 0.39 # mas
        y, x = fpm.shape
        
        mask_xsize = x*fpm_sampling
        mask_ysize = y*fpm_sampling

        spax = input_parameters["spaxel_scale"]
        pix_size = config_data["spaxel_scale"][spax].psfscale
        cube_xsize = cube.shape[2]*pix_size
        cube_ysize = cube.shape[1]*pix_size
        
        xgrid_in = np.linspace(-abs(mask_xsize)*0.5, abs(mask_xsize)*0.5, x)
        ygrid_in = np.linspace(-abs(mask_ysize)*0.5, abs(mask_ysize)*0.5, y)

        xgrid_out = np.arange(-abs(cube_xsize)*0.5, abs(cube_xsize)*0.5, abs(pix_size))
        ygrid_out = np.arange(-abs(cube_ysize)*0.5, abs(cube_ysize)*0.5, abs(pix_size))

        fpm_interp = interp2d(xgrid_in, ygrid_in, fpm, kind='linear')
        fpm_final = fpm_interp(xgrid_out, ygrid_out)
        
        for i in range(cube.shape[0]):
            cube[i,:,:] *= fpm_final
    
    else:
        fpm_final = None

    
    return (cube, back_emission, transmission, fpm_final), LSF_size
