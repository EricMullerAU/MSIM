'''
Rebin 1d and 2d arrays

CHANGELOG:

Version 0.0.0 (2023-10-27)
--------------------------
- Original HARMONI simulator code
Developers: Miguel Pereira Santaella, Laurence Routledge, Simon Zieleniewsk, Sarah Kendrew

Version 1.0.0 (2024-01-10)
--------------------------
- Added progress bars to the interpolation processes
Author: Eric Muller (eric.muller@anu.edu.au)

'''


import numpy as np

#from scipy.interpolate import interp1d
#from scipy.interpolate import interp2d
from scipy.integrate import quad
from tqdm import tqdm # CHANGELOG 09-01-2024: imported for progress bars

def rebin1d(xout, xin, yin):
	"""
	Rebin 1D data to a new grid.

	Args:
		xout (array-like): Output grid values.
		xin (array-like): Input grid values.
		yin (array-like): Input data values.

	Returns:
		array-like: Rebinned data on the output grid.

	"""
	in0 = int(np.interp(xout[0], xin, range(len(xin))))
	
	dx_in = xin[in0+1] - xin[in0]
	dx_out = xout[1] - xout[0]

	if dx_out < dx_in:
		# interpolate if output is finer
		return np.interp(xout, xin, yin)
	else:
		# rebin if output is coarser
		temp = np.zeros((len(xout)), dtype=np.float64)
		#Loop on output values
		box = float(dx_out)/float(dx_in)
		
		in_i = np.interp(xout - dx_out*0.5, xin, range(len(xin)))
		
		for i in tqdm(range(len(xout))): # CHANGELOG 09-01-2024: added a progress bar
			rstart = in_i[i]
			istart = int(rstart)
			if i < len(xout) - 1:
				rstop = in_i[i+1]
			else:
				# for the last one assume the previous box size
				rstop = in_i[i] + (in_i[i] - in_i[i-1])
				
			istop = int(rstop)
			if istop > len(xin) - 1:
				istop = len(xin) - 1
				
			frac1 = rstart - istart
			frac2 = 1.0 - (rstop - istop)
			
			# Add pixel values from istart to istop and subtract
			# fraction pixel from istart to rstart and fraction
			# fraction pixel from rstop to istop.
			if istart == istop:
				temp[i] = (1.0 - frac1 - frac2)*yin[istart]/(rstop - rstart)
			else:
				temp[i] = (np.sum(yin[istart:istop+1]) - frac1*yin[istart] - frac2*yin[istop])/(rstop - rstart)
		
		return np.transpose(temp)

def rebin_cube_1d(xout, xin, cube):
	"""
	Rebins a 3D cube along the first dimension to a new set of output values.

	Args:
		xout (array-like): 1D array of output values.
		xin (array-like): 1D array of input values.
		cube (ndarray): 3D input cube.

	Returns:
		ndarray: Rebinned 3D cube with shape (len(xout), cube.shape[1], cube.shape[2]).

	"""
	# Function implementation
	in0 = int(np.interp(xout[0], xin, range(len(xin))))
	
	dx_in = xin[in0+1] - xin[in0]
	dx_out = xout[1] - xout[0]

	new_cube = np.zeros((len(xout), cube.shape[1], cube.shape[2]), dtype=float)

	if dx_out < dx_in:
		for i in tqdm(np.arange(0, cube.shape[2])): # CHANGELOG 09-01-2024: added a progress bar
			for j in np.arange(0, cube.shape[1]):
				new_cube[:,j,i] = np.interp(xout, xin, cube[:,j,i])
    
		
		return new_cube
	else:
		# rebin if output is coarser
		#Loop on output values
		box = float(dx_out)/float(dx_in)
		in_i = np.interp(xout - dx_out*0.5, xin, range(len(xin)))

		for i in tqdm(range(len(xout))): # CHANGELOG 09-01-2024: added a progress bar
			rstart = in_i[i]
			istart = int(rstart)
			if i < len(xout) - 1:
				rstop = in_i[i+1]
			else:
				# for the last one assume the previous box size
				rstop = in_i[i] + (in_i[i] - in_i[i-1])
				
			istop = int(rstop)
			if istop > len(xin) - 1:
				istop = len(xin) - 1
				
			frac1 = rstart - istart
			frac2 = 1.0 - (rstop - istop)

			new_cube[i,:,:] = (np.sum(cube[istart:istop+1,:,:], axis=0) - frac1*cube[istart,:,:] - frac2*cube[istop,:,:])/(rstop - rstart)


		return new_cube


def frebin2d(array, shape):
	'''
	Function that performs flux-conservative rebinning of an array.

	Args:
		array (numpy.ndarray): The numpy array to be rebinned.
		shape (tuple): The new array size in the format (x, y).

	Returns:
		numpy.ndarray: The new rebinned array with dimensions: shape.
	'''

	#Determine size of input image
	y, x = array.shape

	y1 = y-1
	x1 = x-1

	xbox = x/float(shape[0])
	ybox = y/float(shape[1])


	#Otherwise if not integral contraction
	#First bin in y dimension
	temp = np.zeros((int(shape[1]), x), dtype=np.float64)
	#Loop on output image lines
	#    for i in range(0, int(np.round(shape[1],0)), 1):
	for i in range(0, int(shape[1]), 1):
		rstart = i*ybox
		istart = int(rstart)
		rstop = rstart + ybox
		istop = int(rstop)
		if istop > y1:
			istop = y1
		frac1 = rstart - istart
		frac2 = 1.0 - (rstop - istop)
		
		#Add pixel values from istart to istop an subtract
		#fracion pixel from istart to rstart and fraction
		#fraction pixel from rstop to istop.
		if istart == istop:
			temp[i,:] = (1.0 - frac1 - frac2)*array[istart,:]
		else:
			temp[i,:] = np.sum(array[istart:istop+1,:], axis=0)\
				- frac1*array[istart,:]\
				- frac2*array[istop,:]
		
	temp = np.transpose(temp)

	#Bin in x dimension
	result = np.zeros((int(shape[0]), int(shape[1])), dtype=np.float64)
	#Loop on output image samples
	#    for i in range(0, int(np.round(shape[0],0)), 1):
	for i in range(0, int(shape[0]), 1):
		rstart = i*xbox
		istart = int(rstart)
		rstop = rstart + xbox
		istop = int(rstop)
		if istop > x1:
			istop = x1
		frac1 = rstart - istart
		frac2 = 1.0 - (rstop - istop)
		#Add pixel values from istart to istop an subtract
		#fracion pixel from istart to rstart and fraction
		#fraction pixel from rstop to istop.
		if istart == istop:
			result[i,:] = (1.-frac1-frac2)*temp[istart,:]
		else:
			result[i,:] = np.sum(temp[istart:istop+1,:], axis=0)\
				- frac1*temp[istart,:]\
				- frac2*temp[istop,:]

	return np.transpose(result)/float(xbox*ybox)


