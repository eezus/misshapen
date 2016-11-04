"""
Noteworthy util functions
1. bandpass_default: default bandpass filter
2. phaseT: calculate phase time series
3. ampT: calculate amplitude time series
4. findpt - find peaks and troughs of oscillations
    * _removeboundaryextrema - ignore peaks and troughs along the edge of the signal
5. psd - calculate PSD with one of a few methods

This library contains oscillatory metrics
1. inter_peak_interval - calculate distribution of period lengths of an oscillation
1b estimate_periods - use both the peak and trough intervals to estimate the period
2. peak_voltage - calculate distribution of extrema voltage values
3. bandpow - calculate the power in a frequency band
4. amplitude_variance - calculate variance in the oscillation amplitude
5. frequency_variance - calculate variance in the oscillation frequency
6. lagged coherence - measure of rhythmicity in Fransen et al. 2015
7. oscdetect_ampth - identify periods of oscillations (bursts) in the data using raw voltage thresholds
7a oscdetect_thresh - Detect oscillations using method in Feingold 2015
7b oscdetect_magnorm - Detect oscillations using normalized magnitude of band to broadband
7c signal_to_bursts - extract burst periods from a signal using 1 chosen oscdetect method
7d oscdetect_whitten - extract oscillations using the method described in Whitten et al. 2011
8 bursts_count - count # of bursts
8a bursts_durations - distribution of burst durations
8b bursts_fraction - fraction of time oscillating
9. wfpha - estimate phase of an oscillation using a waveform-based approach
10. slope - calculate slope of the power spectrum
"""

from __future__ import division
import numpy as np
from scipy import signal
import scipy as sp
    
    
def bandpass_default(x, f_range, Fs, rmv_edge = True, w = 3, plot_frequency_response = False):
    """
    Default bandpass filter
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    f_range : (low, high), Hz
        frequency range for narrowband signal of interest
    Fs : float
        The sampling rate
    w : float
        Length of filter order, in cycles. Filter order = ceil(Fs * w / f_range[0])
    rmv_edge : bool
        if True, remove edge artifacts
    plot_frequency_response : bool
        if True, plot the frequency response of the filter
        
    Returns
    -------
    x_filt : array-like 1d
        filtered time series
    taps : array-like 1d
        filter kernel
    """
    
    # Design filter
    Ntaps = np.ceil(Fs*w/f_range[0])
    # Force Ntaps to be odd
    if Ntaps % 2 == 0:
        Ntaps = Ntaps + 1
    taps = sp.signal.firwin(Ntaps, np.array(f_range) / (Fs/2.), pass_zero=False)
    
    # Apply filter
    x_filt = np.convolve(taps,x,'same')
    
    # Plot frequency response
    if plot_frequency_response:
        w, h = signal.freqz(taps)
        
        import matplotlib.pyplot as plt
        plt.figure(figsize=(10,5))
        plt.subplot(1,2,2)
        plt.title('Kernel')
        plt.plot(taps)
        
        plt.subplot(1,2,1)
        plt.plot(w*Fs/(2.*np.pi), 20 * np.log10(abs(h)), 'b')
        plt.title('Frequency response')
        plt.ylabel('Attenuation (dB)', color='b')
        plt.xlabel('Frequency (Hz)')

    # Remove edge artifacts
    N_rmv = int(Ntaps/2.)
    if rmv_edge:
        return x_filt[N_rmv:-N_rmv], Ntaps
    else:
        return x_filt, taps
        
    
def phaseT(x, frange, Fs, rmv_edge = False, filter_fn=None, filter_kwargs=None):
    """
    Calculate the phase and amplitude time series

    Parameters
    ----------
    x : array-like, 1d
        time series
    frange : (low, high), Hz
        The frequency filtering range
    Fs : float, Hz
        The sampling rate
    filter_fn : function
        The filtering function, `filterfn(x, f_range, filter_kwargs)`
    filter_kwargs : dict
        Keyword parameters to pass to `filterfn(.)`

    Returns
    -------
    pha : array-like, 1d
        Time series of phase
    """
    
    if filter_fn is None:
        filter_fn = bandpass_default

    if filter_kwargs is None:
        filter_kwargs = {}


    # Filter signal
    xn, taps = filter_fn(x, frange, Fs, rmv_edge=rmv_edge, **filter_kwargs)
    pha = np.angle(sp.signal.hilbert(xn))

    return pha
    
    
def ampT(x, frange, Fs, rmv_edge = False, filter_fn=None, filter_kwargs=None):
    """
    Calculate the amplitude time series

    Parameters
    ----------
    x : array-like, 1d
        time series
    frange : (low, high), Hz
        The frequency filtering range
    Fs : float, Hz
        The sampling rate
    filter_fn : function
        The filtering function, `filterfn(x, f_range, filter_kwargs)`
    filter_kwargs : dict
        Keyword parameters to pass to `filterfn(.)`

    Returns
    -------
    amp : array-like, 1d
        Time series of phase
    """
    
    if filter_fn is None:
        filter_fn = bandpass_default

    if filter_kwargs is None:
        filter_kwargs = {}


    # Filter signal
    xn, taps = filter_fn(x, frange, Fs, rmv_edge=rmv_edge, **filter_kwargs)
    amp = np.abs(sp.signal.hilbert(xn))

    return amp


def findpt(x, f_range, Fs, boundary = None, forcestart = 'peak',
            filter_fn = bandpass_default, filter_kwargs = {}):
    """
    Calculate peaks and troughs over time series
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    f_range : (low, high), Hz
        frequency range for narrowband signal of interest, used to find 
        zerocrossings of the oscillation
    Fs : float
        The sampling rate (default = 1000Hz)
    boundary : int
        distance from edge of recording that an extrema must be in order to be
        accepted (in number of samples)
    forcestart : str or None
        if 'peak', then force the output to begin with a peak and end in a trough
        if 'trough',  then force the output to begin with a trough and end in peak
        if None, force nothing
    filter_fn : filter function with required inputs (x, f_range, Fs, rmv_edge)
        function to use to filter original time series, x
    filter_kwargs : dict
        keyword arguments to the filter_fn

    Returns
    -------
    Ps : array-like 1d
        indices at which oscillatory peaks occur in the input signal x
    Ts : array-like 1d
        indices at which oscillatory troughs occur in the input signal x
    """

    # Default boundary value as 1 cycle length
    if boundary is None:
        boundary = int(np.ceil(Fs/float(f_range[0])))

    # Filter signal
    xn, taps = filter_fn(x, f_range, Fs, rmv_edge=False, **filter_kwargs)
    
    # Find zero crosses
    def fzerofall(data):
        pos = data > 0
        return (pos[:-1] & ~pos[1:]).nonzero()[0]

    def fzerorise(data):
        pos = data < 0
        return (pos[:-1] & ~pos[1:]).nonzero()[0]

    zeroriseN = fzerorise(xn)
    zerofallN = fzerofall(xn)

    # Calculate # peaks and troughs
    if zeroriseN[-1] > zerofallN[-1]:
        P = len(zeroriseN) - 1
        T = len(zerofallN)
    else:
        P = len(zeroriseN)
        T = len(zerofallN) - 1

    # Calculate peak samples
    Ps = np.zeros(P, dtype=int)
    for p in range(P):
        # Calculate the sample range between the most recent zero rise
        # and the next zero fall
        mrzerorise = zeroriseN[p]
        nfzerofall = zerofallN[zerofallN > mrzerorise][0]
        Ps[p] = np.argmax(x[mrzerorise:nfzerofall]) + mrzerorise

    # Calculate trough samples
    Ts = np.zeros(T, dtype=int)
    for tr in range(T):
        # Calculate the sample range between the most recent zero fall
        # and the next zero rise
        mrzerofall = zerofallN[tr]
        nfzerorise = zeroriseN[zeroriseN > mrzerofall][0]
        Ts[tr] = np.argmin(x[mrzerofall:nfzerorise]) + mrzerofall
        
    if boundary > 0:
        Ps = _removeboundaryextrema(x, Ps, boundary)
        Ts = _removeboundaryextrema(x, Ts, boundary)
        
    # Assure equal # of peaks and troughs by starting with a peak and ending with a trough
    if forcestart == 'peak':
        if Ps[0] > Ts[0]:
            Ts = Ts[1:]
        if Ps[-1] > Ts[-1]:
            Ps = Ps[:-1]
    elif forcestart == 'trough':
        if Ts[0] > Ps[0]:
            Ps = Ps[1:]
        if Ts[-1] > Ps[-1]:
            Ts = Ts[:-1]
    elif forcestart is None:
        pass
    else:
        raise ValueError('Parameter forcestart is invalid')
        
    return Ps, Ts
    
    
def f_psd(x, Fs, method,
        Hzmed=0, welch_params={'window':'hanning','nperseg':1000,'noverlap':None}):
    '''
    Calculate the power spectrum of a signal
    
    Parameters
    ----------
    x : array
        temporal signal
    Fs : integer
        sampling rate
    method : str in ['fftmed','welch]
        Method for calculating PSD
    Hzmed : float
        relevant if method == 'fftmed'
        Frequency width of the median filter
    welch_params : dict
        relevant if method == 'welch'
        Parameters to sp.signal.welch
        
    Returns
    -------
    f : array
        frequencies corresponding to the PSD output
    psd : array
        power spectrum
    '''
    
    if method == 'fftmed':
        # Calculate frequencies
        N = len(x)
        f = np.arange(0,Fs/2,Fs/N)
        
        # Calculate PSD
        rawfft = np.fft.fft(x)
        psd = np.abs(rawfft[:len(f)])**2
    
        # Median filter
        if Hzmed > 0:
            sampmed = np.argmin(np.abs(f-Hzmed/2.0))
            psd = signal.medfilt(psd,sampmed*2+1)
            
    elif method == 'welch':
        f, psd = sp.signal.welch(x, fs=Fs, **welch_params)
        
    else:
        raise ValueError('input for PSD method not recognized')
    
    return f, psd
    
    
def _removeboundaryextrema(x, Es, boundaryS):
    """
    Remove extrema close to the boundary of the recording
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    Es : array-like 1d
        time points of oscillatory peaks or troughs
    boundaryS : int
        Number of samples around the boundary to reject extrema
        
    Returns
    -------
    newEs : array-like 1d
        extremas that are not too close to boundary
    
    """
    
    # Calculate number of samples
    nS = len(x)
    
    # Reject extrema too close to boundary
    SampLims = (boundaryS, nS-boundaryS)
    E = len(Es)
    todelete = []
    for e in range(E):
        if np.logical_or(Es[e]<SampLims[0],Es[e]>SampLims[1]):
            todelete = np.append(todelete,e)
            
    newEs = np.delete(Es,todelete)
    
    return newEs


def inter_peak_interval(Ps):
    """
    Find the distribution of the period durations of neural oscillations as in Hentsche EJN 2007 Fig2
    
    Parameters
    ----------
    Ps : array-like 1d
        Arrays of extrema time points
        
    Returns
    -------
    periods : array-like 1d
        series of intervals between peaks
    """
    
    return np.diff(Ps)
    

def estimate_period(x, f_range, Fs, returnPsTs = False):
    """
    Estimate the length of the period (in samples) of an oscillatory process in signal x in the range f_range
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    f_range : (low, high), Hz
        frequency range for narrowband signal of interest, used to find 
        zerocrossings of the oscillation
    Fs : float
        The sampling rate (default = 1000Hz)
    returnPsTs : boolean
        if True, return peak and trough indices

    Returns
    -------
    period : int
        Estimate of period in samples
    """
    
    # Calculate peaks and troughs
    boundary = int(np.ceil(Fs/float(2*f_range[0])))
    Ps, Ts = findpt(x, f_range, Fs, boundary = boundary)
    
    # Calculate period
    if len(Ps) >= len(Ts):
        period = (Ps[-1] - Ps[0])/(len(Ps)-1)
    else:
        period = (Ts[-1] - Ts[0])/(len(Ts)-1)
        
    if returnPsTs:
        return period, Ps, Ts
    else:
        return period


def peak_voltage(x, Ps):
    """
    Calculate the distribution of voltage of the extrema as in Hentsche EJN 2007 Fig2
    
    Note that this function only returns data while the signal was identified to be in an oscillation,
    using the default oscillation detector
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    Ps : array-like 1d
        Arrays of extrema time points
        
    Returns
    -------
    peak_voltages : array-like 1d
        distribution of the peak voltage values
    """
    return x[Ps]
    
    
def bandpow(x, Fs, flim):
    '''
    Calculate the power in a frequency range
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    Fs : float
        sampling rate
    flim : (lo, hi)
        limits of frequency range
        
    Returns
    -------
    pow : float
        power in the range
    '''
    
    # Calculate PSD
    N = len(x)
    f = np.arange(0,Fs/2,Fs/N)
    rawfft = np.fft.fft(x)
    psd = np.abs(rawfft[:len(f)])**2
    
    # Calculate power
    fidx = np.logical_and(f>=flim[0],f<=flim[1])
    return np.sum(psd[fidx])/np.float(len(f)*2)
    
    
def amplitude_variance(x, Fs, flim):
    '''
    Calculate the variance in the oscillation amplitude
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    Fs : float
        sampling rate
    flim : (lo, hi)
        limits of frequency range
        
    Returns
    -------
    pow : float
        power in the range
    '''
    
    # Calculate amplitude
    amp = ampT(x, flim, Fs)
    return np.var(amp)
    
    
def frequency_variance(x, Fs, flim):
    '''
    Calculate the variance in the instantaneous frequency
    
    NOTE: This function assumes monotonic phase, so a phase slip will be processed as a very high frequency
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    Fs : float
        sampling rate
    flim : (lo, hi)
        limits of frequency range
        
    Returns
    -------
    pow : float
        power in the range
    '''
    
    # Calculate amplitude
    pha = phaseT(x, flim, Fs)
    phadiff = np.diff(pha)
    phadiff[phadiff<0] = phadiff[phadiff<0]+2*np.pi
    inst_freq = Fs*phadiff/(2*np.pi)
    return np.var(inst_freq)
    
    
def lagged_coherence(x, frange, Fs, N_cycles=3, f_step=1, return_spectrum=False):
    """
    Quantify the rhythmicity of a time series using lagged coherence.
    Return the mean lagged coherence in the frequency range as an
    estimate of rhythmicity.
    As in Fransen et al. 2015
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    f_range : (low, high), Hz
        frequency range for narrowband signal of interest, used to find 
        zerocrossings of the oscillation
    Fs : float
        The sampling rate (default = 1000Hz)
    N_cycles : float
        Number of cycles of the frequency of interest to be used in lagged coherence calculate
    f_step : float, Hz
        step size to calculate lagged coherence in the frequency range.
    return_spectrum : bool
        if True, return the lagged coherence for all frequency values. otherwise, only return mean
    fourier_or_wavelet : string {'fourier', 'wavelet'}
        NOT IMPLEMENTED. ONLY FOURIER
        method for estimating phase.
        fourier: calculate fourier coefficients for each time window. hanning tpaer.
        wavelet: multiply each window by a N-cycle wavelet
        
    Returns
    -------
    rhythmicity : float
        mean lagged coherence value in the frequency range of interest
    """
    # Identify Fourier components of interest
    freqs = np.arange(frange[0],frange[1]+f_step,f_step)
    
    # Calculate lagged coherence for each frequency
    F = len(freqs)
    lcs = np.zeros(F)
    for i,f in enumerate(freqs):
        lcs[i] = _lagged_coherence_1freq(x, f, Fs, N_cycles=N_cycles, f_step=f_step)
        
    if return_spectrum:
        return lcs
    else:
        return np.mean(lcs)
    
    
def _lagged_coherence_1freq(x, f, Fs, N_cycles=3, f_step=1):
    """Calculate lagged coherence of x at frequency f using the hanning-taper FFT method"""
    Nsamp = int(np.ceil(N_cycles*Fs / f))
    # For each N-cycle chunk, calculate phase
    chunks = _nonoverlapping_chunks(x,Nsamp)
    C = len(chunks)
    hann_window = signal.hanning(Nsamp)
    fourier_f = np.fft.fftfreq(Nsamp,1/float(Fs))
    fourier_f_idx = _arg_closest_value(fourier_f,f)
    fourier_coefsoi = np.zeros(C,dtype=complex)
    for i2, c in enumerate(chunks):
        fourier_coef = np.fft.fft(c*hann_window)
        
        fourier_coefsoi[i2] = fourier_coef[fourier_f_idx]

    lcs_num = 0
    for i2 in range(C-1):
        lcs_num += fourier_coefsoi[i2]*np.conj(fourier_coefsoi[i2+1])
    lcs_denom = np.sqrt(np.sum(np.abs(fourier_coefsoi[:-1])**2)*np.sum(np.abs(fourier_coefsoi[1:])**2))
    return np.abs(lcs_num/lcs_denom)
    

def _nonoverlapping_chunks(x, N):
    """Split x into nonoverlapping chunks of length N"""
    Nchunks = int(np.floor(len(x)/float(N)))
    chunks = np.reshape(x[:int(Nchunks*N)],(Nchunks,int(N)))
    return chunks
    

def _arg_closest_value(x, val):
    """Find the index of closest value in x to val"""
    return np.argmin(np.abs(x-val))
    
    
def oscdetect_ampth(x, f_range, Fs, thresh_hi, thresh_lo,
                    min_osc_periods = 3, filter_fn = bandpass_default, filter_kwargs = {}, return_amp=False):
    """
    Detect the time range of oscillations in a certain frequency band.
    * METHOD: Set 2 VOLTAGE thresholds.
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    f_range : (low, high), Hz
        frequency range for narrowband signal of interest
    Fs : float
        The sampling rate
    thresh_hi : float
        minimum magnitude-normalized value in order to force an oscillatory period
    thresh_lo : float
        minimum magnitude-normalized value to be included in an existing oscillatory period
    magnitude : string in ('power', 'amplitude')
        metric of magnitude used for thresholding
    baseline : string in ('median', 'mean')
        metric to normalize magnitude used for thresholding
    min_osc_periods : float
        minimum length of an oscillatory period in terms of the period length of f_range[0]
    filter_fn : filter function with required inputs (x, f_range, Fs, rmv_edge)
        function to use to filter original time series, x
    filter_kwargs : dict
        keyword arguments to the filter_fn
        
    Returns
    -------
    isosc : array-like 1d
        binary time series. 1 = in oscillation; 0 = not in oscillation
    taps : array-like 1d
        filter kernel
    """
    
    # Filter signal
    x_filt, taps = filter_fn(x, f_range, Fs, rmv_edge=False, **filter_kwargs)
    
    # Quantify magnitude of the signal
    x_amplitude = np.abs(sp.signal.hilbert(x_filt))

    # Identify time periods of oscillation
    isosc = _2threshold_split(x_amplitude, thresh_hi, thresh_lo)
    
    # Remove short time periods of oscillation
    min_period_length = int(np.ceil(min_osc_periods*Fs/f_range[0]))
    isosc_noshort = _rmv_short_periods(isosc, min_period_length)
    
    if return_amp:
        return isosc_noshort, taps, x_amplitude
    else:
        return isosc_noshort, taps
    
        
def _2threshold_split(x, thresh_hi, thresh_lo):
    """Identify periods of a time series that are above thresh_lo and have at least one value above thresh_hi"""
    
    # Find all values above thresh_hi
    x[[0,-1]] = 0 # To avoid bug in later loop, do not allow first or last index to start off as 1
    idx_over_hi = np.where(x >= thresh_hi)[0]

    # Initialize values in identified period
    positive = np.zeros(len(x))
    positive[idx_over_hi] = 1
    
    # Iteratively test if a value is above thresh_lo if it is not currently in an identified period
    lenx = len(x)
    for i in idx_over_hi:
        j_down = i-1
        if positive[j_down] == 0:
            j_down_done = False
            while j_down_done is False:
                if x[j_down] >= thresh_lo:
                    positive[j_down] = 1
                    j_down -= 1
                    if j_down < 0:
                        j_down_done = True
                else:
                    j_down_done = True
                    
        j_up = i+1
        if positive[j_up] == 0:
            j_up_done = False
            while j_up_done is False:
                if x[j_up] >= thresh_lo:
                    positive[j_up] = 1
                    j_up += 1
                    if j_up >= lenx:
                        j_up_done = True
                else:
                    j_up_done = True
    
    return positive


def _rmv_short_periods(x, N):
    """Remove periods that ==1 for less than N samples"""
    
    if np.sum(x)==0:
        return x
        
    osc_changes = np.diff(x)
    osc_starts = np.where(osc_changes==1)[0]
    osc_ends = np.where(osc_changes==-1)[0]

    if len(osc_starts)==0:
        osc_starts = [0]
    if len(osc_ends)==0:
        osc_ends = [len(osc_changes)]

    if osc_ends[0] < osc_starts[0]:
        osc_starts = np.insert(osc_starts, 0, 0)
    if osc_ends[-1] < osc_starts[-1]:
        osc_ends = np.append(osc_ends, len(osc_changes))

    osc_length = osc_ends - osc_starts
    osc_starts_long = osc_starts[osc_length>=N]
    osc_ends_long = osc_ends[osc_length>=N]

    is_osc = np.zeros(len(x))
    for osc in range(len(osc_starts_long)):
        is_osc[osc_starts_long[osc]:osc_ends_long[osc]] = 1
    return is_osc
    
    
def oscdetect_thresh(x, f_range, Fs, thresh_hi = 3, thresh_lo = 1.5, magnitude = 'power', baseline = 'median',
                    min_osc_periods = 3, filter_fn = bandpass_default, filter_kwargs = {}, return_normmag=False):
    """
    Detect the time range of oscillations in a certain frequency band.
    Based on Feingold 2015 PNAS Fig. 4
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    f_range : (low, high), Hz
        frequency range for narrowband signal of interest
    Fs : float
        The sampling rate
    thresh_hi : float
        minimum magnitude-normalized value in order to force an oscillatory period
    thresh_lo : float
        minimum magnitude-normalized value to be included in an existing oscillatory period
    magnitude : string in ('power', 'amplitude')
        metric of magnitude used for thresholding
    baseline : string in ('median', 'mean')
        metric to normalize magnitude used for thresholding
    min_osc_periods : float
        minimum length of an oscillatory period in terms of the period length of f_range[0]
    filter_fn : filter function with required inputs (x, f_range, Fs, rmv_edge)
        function to use to filter original time series, x
    filter_kwargs : dict
        keyword arguments to the filter_fn
        
    Returns
    -------
    isosc : array-like 1d
        binary time series. 1 = in oscillation; 0 = not in oscillation
    taps : array-like 1d
        filter kernel
    """
    
    # Filter signal
    x_filt, taps = filter_fn(x, f_range, Fs, rmv_edge=False, **filter_kwargs)
    
    # Quantify magnitude of the signal
    ## Calculate amplitude
    x_amplitude = np.abs(sp.signal.hilbert(x_filt))
    ## Set magnitude as power or amplitude
    if magnitude == 'power':
        x_magnitude = x_amplitude**2
    elif magnitude == 'amplitude':
        x_magnitude = x_amplitude
    else:
        raise ValueError("Invalid 'magnitude' parameter")
        
    # Calculate normalized magnitude
    if baseline == 'median':
        norm_mag = x_magnitude / np.median(x_magnitude)
    elif baseline == 'mean':
        norm_mag = x_magnitude / np.mean(x_magnitude)
    else:
        raise ValueError("Invalid 'baseline' parameter")

    # Identify time periods of oscillation
    isosc = _2threshold_split(norm_mag, thresh_hi, thresh_lo)
    
    # Remove short time periods of oscillation
    min_period_length = int(np.ceil(min_osc_periods*Fs/f_range[0]))
    isosc_noshort = _rmv_short_periods(isosc, min_period_length)
    
    if return_normmag:
        return isosc_noshort, taps, norm_mag
    else:
        return isosc_noshort, taps
    

def oscdetect_magnorm(x, f_range, Fs, thresh_hi = .3, thresh_lo = .1, magnitude = 'power', thresh_bandpow_pc = 20,
                     min_osc_periods = 3, filter_fn = bandpass_default, filter_kwargs = {'w':7}):
    """
    Detect the time range of oscillations in a certain frequency band.
    Based on Feingold 2015 PNAS Fig. 4 except normalize the magnitude measure by the overall power or amplitude
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    f_range : (low, high), Hz
        frequency range for narrowband signal of interest
    Fs : float
        The sampling rate
    thresh_hi : float
        minimum magnitude fraction needed in order to force an oscillatory period
    thresh_lo : float
        minimum magnitude fraction needed to be included in an existing oscillatory period
    magnitude : string in ('power', 'amplitude')
        metric of magnitude used for thresholding
    thresh_bandpow_pc : float (0 to 100)
        percentile cutoff for 
    min_osc_periods : float
        minimum length of an oscillatory period in terms of the period length of f_range[0]
    filter_fn : filter function with required inputs (x, f_range, Fs, rmv_edge)
        function to use to filter original time series, x
    filter_kwargs : dict
        keyword arguments to the filter_fn
        
    Returns
    -------
    isosc : array-like 1d
        binary time series. 1 = in oscillation; 0 = not in oscillation
    taps : array-like 1d
        filter kernel
    """
    
    # Filter signal
    x_filt, taps = filter_fn(x, f_range, Fs, rmv_edge=False, **filter_kwargs)
    
    # Quantify magnitude of the signal
    ## Calculate amplitude
    x_amplitude = np.abs(sp.signal.hilbert(x_filt))
    ## Calculate overall signal amplitude
    ## NOTE: I'm pretty sure this is right, not 100% sure
    taps_env = np.abs(sp.signal.hilbert(taps)) # This is the amplitude of the filter
    x_overallamplitude = np.abs(np.convolve(np.abs(x), taps_env, mode='same')) # The amplitude at a point in time is a measure of the neural activity with a decaying weight over time like that of the amplitude of the filter
    ## Set magnitude as power or amplitude
    if magnitude == 'power':
        frac_magnitude = (x_amplitude/x_overallamplitude)**2
    elif magnitude == 'amplitude':
        frac_magnitude = (x_amplitude/x_overallamplitude)
    else:
        raise ValueError("Invalid 'magnitude' parameter")
        
    # Identify time periods of oscillation
    isosc = _2threshold_split_magnorm(frac_magnitude, thresh_hi, thresh_lo, x_amplitude, thresh_bandpow_pc)
    
    # Remove short time periods of oscillation
    min_period_length = int(np.ceil(min_osc_periods*Fs/f_range[0]))
    isosc_noshort = _rmv_short_periods(isosc, min_period_length)
    
    return isosc_noshort, taps

    
def _2threshold_split_magnorm(frac_mag, thresh_hi, thresh_lo, band_mag, thresh_bandpow_pc):
    """Identify periods of a time series that are above thresh_lo and have at least one value above thresh_hi.
        There is the additional requirement that the band magnitude must be above a chosen percentile threshold."""
    
    # Find all values above thresh_hi
    frac_mag[[0,-1]] = 0 # To avoid bug in later loop, do not allow first or last index to start off as 1
    bandmagpc = np.percentile(band_mag,thresh_bandpow_pc)
    idx_over_hi = np.where(np.logical_and(frac_mag >= thresh_hi, band_mag >= bandmagpc))[0]
    if len(idx_over_hi) == 0:
        raise ValueError('No oscillatory periods found. Change thresh_hi or bandmagpc parameters.')

    # Initialize values in identified period
    positive = np.zeros(len(frac_mag))
    positive[idx_over_hi] = 1
    
    # Iteratively test if a value is above thresh_lo if it is not currently in an identified period
    lenx = len(frac_mag)
    for i in idx_over_hi:
        j_down = i-1
        if positive[j_down] == 0:
            j_down_done = False
            while j_down_done is False:
                if np.logical_and(frac_mag[j_down] >= thresh_lo,band_mag[j_down] >= bandmagpc):
                    positive[j_down] = 1
                    j_down -= 1
                    if j_down < 0:
                        j_down_done = True
                else:
                    j_down_done = True
                    
        j_up = i+1
        if positive[j_up] == 0:
            j_up_done = False
            while j_up_done is False:
                if np.logical_and(frac_mag[j_up] >= thresh_lo,band_mag[j_up] >= bandmagpc):
                    positive[j_up] = 1
                    j_up += 1
                    if j_up >= lenx:
                        j_up_done = True
                else:
                    j_up_done = True
    
    return positive
    
    
def oscdetect_whitten(x, f_range, Fs, thresh_hi = 3, thresh_lo = 1.5, magnitude = 'power', baseline = 'median',
                    min_osc_periods = 3, filter_fn = bandpass_default, filter_kwargs = {}, return_normmag=False):
    """
    Detect the time range of oscillations in a certain frequency band.
    Based on Whitten et al. 2011
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    f_range : (low, high), Hz
        frequency range for narrowband signal of interest
    Fs : float
        The sampling rate
    thresh_hi : float
        minimum magnitude-normalized value in order to force an oscillatory period
    thresh_lo : float
        minimum magnitude-normalized value to be included in an existing oscillatory period
    magnitude : string in ('power', 'amplitude')
        metric of magnitude used for thresholding
    baseline : string in ('median', 'mean')
        metric to normalize magnitude used for thresholding
    min_osc_periods : float
        minimum length of an oscillatory period in terms of the period length of f_range[0]
    filter_fn : filter function with required inputs (x, f_range, Fs, rmv_edge)
        function to use to filter original time series, x
    filter_kwargs : dict
        keyword arguments to the filter_fn
        
    Returns
    -------
    isosc : array-like 1d
        binary time series. 1 = in oscillation; 0 = not in oscillation
    taps : array-like 1d
        filter kernel
    """
    
    raise NotImplementedError('Function not written yet')
    
    # Calculate PSD
    
    # Calculate slope
    
    
    
    # CHANGE BELOW IS OLD
    
    # Filter signal
    x_filt, taps = filter_fn(x, f_range, Fs, rmv_edge=False, **filter_kwargs)
    
    # Quantify magnitude of the signal
    ## Calculate amplitude
    x_amplitude = np.abs(sp.signal.hilbert(x_filt))
    ## Set magnitude as power or amplitude
    if magnitude == 'power':
        x_magnitude = x_amplitude**2
    elif magnitude == 'amplitude':
        x_magnitude = x_amplitude
    else:
        raise ValueError("Invalid 'magnitude' parameter")
        
    # Calculate normalized magnitude
    if baseline == 'median':
        norm_mag = x_magnitude / np.median(x_magnitude)
    elif baseline == 'mean':
        norm_mag = x_magnitude / np.mean(x_magnitude)
    else:
        raise ValueError("Invalid 'baseline' parameter")

    # Identify time periods of oscillation
    isosc = _2threshold_split(norm_mag, thresh_hi, thresh_lo)
    
    # Remove short time periods of oscillation
    min_period_length = int(np.ceil(min_osc_periods*Fs/f_range[0]))
    isosc_noshort = _rmv_short_periods(isosc, min_period_length)
    
    if return_normmag:
        return isosc_noshort, taps, norm_mag
    else:
        return isosc_noshort, taps


def signal_to_bursts(x, f_range, Fs, burst_fn = None, burst_kwargs = None):
    """
    Separate a signal into time periods of oscillatory bursts
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    f_range : (low, high), Hz
        frequency range for narrowband signal of interest
    Fs : float
        The sampling rate
    burst_fn : burst detector function with required inputs (x, f_range, Fs, rmv_edge)
        function to use to filter original time series, x
    burst_kwargs : dict
        keyword arguments to the burst_fn
        
    Returns
    -------
    x_bursts : numpy array of array-like 1d
        array of each bursting period in x
    burst_filter : array-like 1d
        filter kernel used in identifying bursts
    """
    
    # Initialize burst detection parameters
    if burst_fn is None:
        burst_fn = oscdetect_thresh

    if burst_kwargs is None:
        burst_kwargs = {}
        
    # Apply burst detection
    isburst, burst_filter = burst_fn(x, f_range, Fs, **burst_kwargs)
    
    # Confirm burst detection
    if np.sum(isburst) == 0:
        print('No bursts detected. Adjust burst detector settings or reject signal.')
        return None, None
    
    # Separate x into bursts
    x_bursts = _binarytochunk(x, isburst)
    return x_bursts, burst_filter
    
    
def _binarytochunk(x, binary_array):
    """Outputs chunks of x in which binary_array is continuously 1"""
    
    # Find beginnings and ends of bursts
    binary_diffs = np.diff(binary_array)
    binary_diffs = np.insert(binary_diffs, 0, 0)
    begin_bursts = np.where(binary_diffs == 1)[0]
    end_bursts = np.where(binary_diffs == -1)[0]
    
    # Identify if bursts lie at the beginning or end of recording
    if begin_bursts[0] > end_bursts[0]:
        begin_bursts = np.insert(begin_bursts, 0, 0)
    if begin_bursts[-1] > end_bursts[-1]:
        end_bursts = np.append(end_bursts, len(x))
        
    # Make array of each burst
    Nbursts = len(begin_bursts)
    bursts = np.zeros(Nbursts, dtype=object)
    for b in range(Nbursts):
        bursts[b] = x[begin_bursts[b]:end_bursts[b]]
    
    return bursts
    

def bursts_count(bursts_binary):
    """Calculate number of bursts based off the binary burst indicator"""
    # Find beginnings and ends of bursts
    if np.sum(bursts_binary)==0:
        return 0
        
    binary_diffs = np.diff(bursts_binary)
    binary_diffs = np.insert(binary_diffs, 0, 0)
    begin_bursts = np.where(binary_diffs == 1)[0]
    end_bursts = np.where(binary_diffs == -1)[0]

    if len(begin_bursts)==0:
       begin_bursts = [0]
    if len(end_bursts)==0:
        end_bursts = [len(binary_diffs)]
    
    # Identify if bursts lie at the beginning or end of recording
    if begin_bursts[0] > end_bursts[0]:
        begin_bursts = np.insert(begin_bursts, 0, 0)
    return len(begin_bursts)
    
    
def bursts_fraction(bursts_binary):
    """Calculate fraction of time bursting"""
    return np.mean(bursts_binary)
    
    
def bursts_durations(bursts_binary, Fs):
    """Calculate the duration of each burst"""
    # Find beginnings and ends of bursts
    if np.sum(bursts_binary)==0:
        return 0
        
    binary_diffs = np.diff(bursts_binary)
    binary_diffs = np.insert(binary_diffs, 0, 0)
    begin_bursts = np.where(binary_diffs == 1)[0]
    end_bursts = np.where(binary_diffs == -1)[0]

    if len(begin_bursts)==0:
        begin_bursts = [0]
    if len(end_bursts)==0:
        end_bursts = [len(binary_diffs)]
    
    # Identify if bursts lie at the beginning or end of recording
    if begin_bursts[0] > end_bursts[0]:
        begin_bursts = np.insert(begin_bursts, 0, 0)
    if begin_bursts[-1] > end_bursts[-1]:
        end_bursts = np.append(end_bursts, len(bursts_binary))
        
    # Make array of each burst
    Nbursts = len(begin_bursts)
    lens = np.zeros(Nbursts, dtype=object)
    for b in range(Nbursts):
        lens[b] = end_bursts[b] - begin_bursts[b]
    lens = lens/float(Fs)
    return lens
    

def wfpha(x, Ps, Ts):
    """
    Use peaks and troughs calculated with findpt to calculate an instantaneous
    phase estimate over time
    
    Parameters
    ----------
    x : array-like 1d
        voltage time series
    Ps : array-like 1d
        time points of oscillatory peaks
    Ts : array-like 1d
        time points of oscillatory troughs
        
    Returns
    -------
    pha : array-like 1d
        instantaneous phase
    """

    # Initialize phase array
    L = len(x)
    pha = np.empty(L)
    pha[:] = np.NAN
    
    pha[Ps] = 0
    pha[Ts] = -np.pi

    # Interpolate to find all phases
    marks = np.logical_not(np.isnan(pha))
    t = np.arange(L)
    marksT = t[marks]
    M = len(marksT)
    for m in range(M - 1):
        idx1 = marksT[m]
        idx2 = marksT[m + 1]

        val1 = pha[idx1]
        val2 = pha[idx2]
        if val2 <= val1:
            val2 = val2 + 2 * np.pi

        phatemp = np.linspace(val1, val2, idx2 - idx1 + 1)
        pha[idx1:idx2] = phatemp[:-1]

    # Interpolate the boundaries with the same rate of change as the adjacent
    # sections
    idx = np.where(np.logical_not(np.isnan(pha)))[0][0]
    val = pha[idx]
    dval = pha[idx + 1] - val
    startval = val - dval * idx
    # .5 for nonambiguity in arange length
    pha[:idx] = np.arange(startval, val - dval * .5, dval)

    idx = np.where(np.logical_not(np.isnan(pha)))[0][-1]
    val = pha[idx]
    dval = val - pha[idx - 1]
    dval = np.angle(np.exp(1j * dval))  # Trestrict dval to between -pi and pi
    # .5 for nonambiguity in arange length
    endval = val + dval * (len(pha) - idx - .5)
    pha[idx:] = np.arange(val, endval, dval)

    # Restrict phase between -pi and pi
    pha = np.angle(np.exp(1j * pha))

    return pha
    
    
def slope(f, psd, fslopelim = (80,200), flatten_thresh = 0):
    '''
    Calculate the slope of the power spectrum
    
    Parameters
    ----------
    f : array
        frequencies corresponding to power spectrum
    psd : array
        power spectrum
    fslopelim : 2-element list
        frequency range to fit slope
    flatten_thresh : float
        See foof.utils
        
    Returns
    -------
    slope : float
        slope of psd
    slopelineP : array
        linear fit of the PSD in log-log space (includes information of offset)
    slopelineF : array
        frequency array corresponding to slopebyf
    
    '''
    fslopeidx = np.logical_and(f>=fslopelim[0],f<=fslopelim[1])
    slopelineF = f[fslopeidx]
    
    x = np.log10(slopelineF)
    y = np.log10(psd[fslopeidx])

    from sklearn import linear_model
    lm = linear_model.RANSACRegressor(random_state=42)
    lm.fit(x[:, np.newaxis], y)
    slopelineP = lm.predict(x[:, np.newaxis])
    psd_flat = y - slopelineP.flatten()
    mask = (psd_flat / psd_flat.max()) < flatten_thresh
    psd_flat[mask] = 0
    slopes = lm.estimator_.coef_
    slopes = slopes[0]

    return slopes, slopelineP, slopelineF