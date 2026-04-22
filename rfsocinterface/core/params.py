"""Handle RFSoC Parameter Files"""

import inspect
import logging
from pathlib import Path
import pdb

import numpy as np
import numpy.typing as npt
import h5py

from rfsocinterface.core.utils import DEFAULT_PARAMS_DIRECTORY, PERMISSIONS_ALL_FULL, get_params_file_template, pad_to_length, ensure_path, mHz_formatter


_logger = logging.getLogger(__name__)


PARAM_FILE_N_TONE_ATTRIBUTES = [
    'baseband_freqs',
    'tone_powers',
    'detector_delta_x',
    'detector_delta_y',
    'detector_pol',
    'detector_beam_ampl',
    'dfoverf_per_mK',
    'chanmask',
]


def initialize_params_file(
    tile_name: str,
    baseband_freqs: npt.NDArray,
    lo_freq: float,
    params_dir: Path=DEFAULT_PARAMS_DIRECTORY,
):
    params_tile_file = Path(get_params_file_template(tile_name, params_dir=params_dir))
    if not params_tile_file.exists():
        params_tile_file.touch(PERMISSIONS_ALL_FULL)
    n_tones = np.size(baseband_freqs)
    with h5py.File(params_tile_file, 'w') as params_fh:
        params_fh.attrs['n_tones'] = n_tones
        params_fh.attrs['tile_name'] = tile_name
        params_fh.attrs['tile_number'] = 0
        params_fh.attrs['chan_number'] = 0
        params_fh.attrs['ifslice_number'] = 0
        params_fh.attrs['lo_freq'] = lo_freq
        params_fh.create_dataset(
            'chanmask',
            shape=(n_tones,),
            maxshape=(1024,),
            dtype=np.int8,
            fillvalue=1,
        )
        params_fh.create_dataset(
            'chanmask_non_collided',
            shape=(n_tones,),
            maxshape=(1024,),
            dtype=np.int8,
            fillvalue=1,
        )
        params_fh.create_dataset(
            'chanmask_isolated',
            shape=(n_tones,),
            maxshape=(1024,),
            dtype=np.int8,
            fillvalue=1,
        )
        params_fh.create_dataset(
            'baseband_freqs',
            data=baseband_freqs,
            maxshape=(1024,),
        )
        params_fh.create_dataset(
            'tone_powers',
            data=np.ones(n_tones, dtype=np.float32),
            maxshape=(1024,),
        )
        params_fh.create_dataset(
            'detector_delta_x',
            shape=(n_tones,),
            dtype=np.float32,
            maxshape=(1024,),
        )
        params_fh.create_dataset(
            'detector_delta_y',
            shape=(n_tones,),
            dtype=np.float32,
            maxshape=(1024,),
        )
        params_fh.create_dataset(
            'detector_beam_ampl',
            shape=(n_tones,),
            dtype=np.float32,
            maxshape=(1024,),
            fillvalue=1,
        )
        params_fh.create_dataset(
            'detector_pol',
            shape=(n_tones,),
            dtype=np.int8,
            maxshape=(1024,),
            fillvalue=1,
        )
        params_fh.create_dataset(
            'dfoverf_per_mK',
            shape=(n_tones,),
            dtype=np.float64,
            maxshape=(1024,),
            fillvalue=1,
        )
    _logger.info(f'Initialized params file {params_tile_file}')


def update_params_file(
    target: str,
    params_dir: Path=DEFAULT_PARAMS_DIRECTORY,
    baseband_freqs: npt.NDArray=None,
    lo_freq: float=None,
    detector_delta_x: npt.NDArray=None,
    detector_delta_y: npt.NDArray=None,
    detector_beam_ampl: npt.NDArray=None,
    detector_pol: npt.NDArray=None,
    dfoverf_per_mK: npt.NDArray=None,
    chanmask: npt.NDArray=None,
    chanmask_non_collided: npt.NDArray=None,
    chanmask_isolated: npt.NDArray=None,
    tone_powers: npt.NDArray=None,
):
    if Path(target).exists:
        # the first argument was the path to the file
        params_tile_file = Path(target)
    else:
        # the first argument was the name of the tile
        params_tile_file = Path(get_params_file_template(target, params_dir=params_dir))
        if not params_tile_file.exists():
            raise FileExistsError(f'Params file {params_tile_file} does not exist')

    signature = inspect.signature(update_params_file)
    keyword_args = {
        param.name: param.default
        for param in signature.parameters.values()
        if param.default is not inspect.Parameter.empty
    }

    with h5py.File(params_tile_file, 'a') as fh:
        if baseband_freqs is not None:
            fh.attrs['n_tones'] = len(baseband_freqs)
            # TODO: need to extend existing arrays to match the new number of tones

        for k in keyword_args:  # Check all of the keyword arguments
            if k == 'params_dir':
                continue  # We only care about the parameters
            if k == 'lo_freq' and lo_freq is not None:
                fh.attrs['lo_freq'] = lo_freq
                continue
            v = locals()[k]
            if v is None:
                continue  # The value is not being updated, so skip it
            # Check the array is the correct size if needed
            if k in PARAM_FILE_N_TONE_ATTRIBUTES:
                if np.size(v) != fh.attrs['n_tones']:
                    raise ValueError(
                        f'{k} size {np.size(v)} does not match n_tones {fh.attrs["n_tones"]}'
                    )
            fh[k][:] = v


@ensure_path(0)
def add_off_resonance_tones(
    params_file: Path,
    n_offres: int,
    f_min: float,
    f_max: float,
    q: float=1/1000.,
    delta_offres_min: float=1e6,
    collision_threshold: float=1/2000,
):
    """Add off-resonance tones to an existing params file. 
    
    Off-resonance tones are added in the gaps between on-resonance tones, with more 
    spacing between tones at higher frequencies.

    Arguments:
        params_file (Path): Path to the params file to update.
        n_offres (int): Number of offres tones to add.
        f_min (float): Minimum frequency (Hz) of tones to add.
        f_max (float): Maximum frequency (Hz) of tones to add.
        q (float, optional): Fractional frequency spacing to consider a tone far enough
            from on-resonance tones. Defaults to 1/1000.
        delta_offres_min (float, optional): Minimum spacing (Hz) between offres tones at
            the LO frequency. Defaults to 1e5.
        collision_threshold (float): Maximum fractional separation between collided 
            resonances. Defaults to 1/2000.
    """
    with h5py.File(params_file, 'a') as params_file:
        baseband_freqs = params_file['baseband_freqs'][:]
        chanmask = params_file['chanmask'][:]
        if 'lo_freq' not in params_file.attrs:
            lo_freq = params_file['lo_freq'][()]
        else:
            lo_freq = params_file.attrs['lo_freq']
        tone_powers = params_file['tone_powers'][:]
        detdx = params_file['detector_delta_x'][:]
        detdy = params_file['detector_delta_y'][:]
        det_beam_ampl = params_file['detector_beam_ampl'][:]
        detector_pol = params_file['detector_pol'][:]
        dfoverf_per_mK = params_file['dfoverf_per_mK'][:]

    # Find collided resonances
    shift1 = np.abs(baseband_freqs - np.roll(baseband_freqs, 1))
    shift2 = np.abs(np.roll(baseband_freqs, -1) - baseband_freqs)
    nearest_res = np.abs(np.minimum(shift1, shift2) / baseband_freqs)
    collided_ind = np.argwhere(nearest_res < collision_threshold)
    chanmask[collided_ind] = -1

    offres_tones = []
    tones_left = n_offres
    freqs_in_range = baseband_freqs[
        (baseband_freqs + lo_freq >= f_min) &
        (baseband_freqs + lo_freq <= f_max)
    ]

    freqs_in_range = np.concatenate(([f_min - lo_freq], freqs_in_range, [f_max - lo_freq]))
    gaps = np.diff(freqs_in_range)
    sorted_gap_ind = np.argsort(gaps)[::-1]
    # for f0, f1 in zip(freqs_in_range[:-1], freqs_in_range[1:]):
    import matplotlib.pyplot as plt
    for i_gap in sorted_gap_ind:
        f0 = freqs_in_range[i_gap]
        f1 = freqs_in_range[i_gap + 1]
        if tones_left == 0:
            break
        search_range = (f0 + np.abs(f0 * q), f1 - np.abs(f1 * q))
        # Insert as many off-resonance tones that will fit in the gap
        # Tones should be further apart as the frequency increases
        # spacing_scale = np.abs((f0 + f1) / 2) / lo_freq
        # this_offres_tones = np.arange(
        #     search_range[0],
        #     search_range[1],
        #     delta_offres_min * spacing_scale,
        # )
        offres = []
        this_f = search_range[0]
        while this_f <= search_range[1]:
            offres.append(this_f)
            diff = delta_offres_min * np.abs((this_f + lo_freq) / lo_freq)
            print(f'{this_f * 1e-6:.4f} + {diff * 1e-6:.3f}')
            # if np.abs(this_f - 2.3e6) < 1e6:
            #     pdb.set_trace()
            this_f += diff
        this_offres_tones = np.array(offres)
        # pdb.set_trace()
        # equally_spaced = np.arange(search_range[0], search_range[1], delta_offres_min)
        # spacing_scale = equally_spaced / lo_freq
        # offres = np.cumsum(spacing_scale)
        # offres_1 = offres[(offres >= search_range[0]) & (offres <= search_range[1])]
        offres_tones.extend(this_offres_tones[:tones_left])
        tones_left -= len(this_offres_tones[:tones_left])

    # Restrict off-resonance tones to be within f_min and f_max
    offres_tones = np.array(offres_tones)
    offres_tones = offres_tones[
        (offres_tones + lo_freq >= f_min) &
        (offres_tones + lo_freq <= f_max)
    ]
    # Create new arrays with offres tones added in the correct locations
    tones_added = len(offres_tones)
    all_tones = np.concatenate((baseband_freqs, offres_tones))
    sorted_ind = np.argsort(all_tones)

    new_baseband_freqs = all_tones[sorted_ind]
    new_chanmask = np.concatenate((chanmask, np.zeros(tones_added, dtype=np.int8)))[sorted_ind]



    new_tone_powers = np.concatenate((tone_powers, np.ones(tones_added, dtype=np.float32)))[sorted_ind]
    new_detdx = np.concatenate((detdx, np.zeros(tones_added, dtype=np.float32)))[sorted_ind]
    new_detdy = np.concatenate((detdy, np.zeros(tones_added, dtype=np.float32)))[sorted_ind]
    new_det_beam_ampl = np.concatenate((det_beam_ampl, np.ones(tones_added, dtype=np.float32)))[sorted_ind]
    new_detector_pol = np.concatenate((detector_pol, np.ones(tones_added, dtype=np.int8)))[sorted_ind]
    new_dfoverf_per_mK = np.concatenate((dfoverf_per_mK, np.ones(tones_added, dtype=np.float64)))[sorted_ind]

    import matplotlib.pyplot as plt
    plt.figure()
    onres_ind = np.argwhere(new_chanmask == 1).flatten()
    plt.stem(new_baseband_freqs[onres_ind], new_tone_powers[onres_ind], linefmt='b', markerfmt='none', basefmt='none',label='On-resonance tones')
    if tones_added > 0:
        offres_ind = np.argwhere(new_chanmask == 0).flatten()
        plt.stem(new_baseband_freqs[offres_ind], new_tone_powers[offres_ind], linefmt='orange', markerfmt='none', basefmt='none', label='Off-resonance tones')
    if collided_ind.size > 0:
        plt.stem(new_baseband_freqs[collided_ind], new_tone_powers[collided_ind], linefmt='r', markerfmt='none', basefmt='none',label='Collided Resonances')
    plt.axvline(f_min - lo_freq, color='black', linestyle='--')
    plt.axvline(f_max - lo_freq, color='black', linestyle='--')
    plt.xlabel('Baseband Frequency (MHz)')
    plt.ylabel('Tone Power')
    plt.gca().xaxis.set_major_formatter(mHz_formatter)
    plt.title('On-resonance and Off-resonance Tones')
    plt.legend()
    plt.show()

    pdb.set_trace()

    update_params_file(
        params_file.name,
        params_dir=params_file.parent,
        baseband_freqs=new_baseband_freqs,
        chanmask=new_chanmask,
        tone_powers=new_tone_powers,
        detector_delta_x=new_detdx,
        detector_delta_y=new_detdy,
        detector_beam_ampl=new_det_beam_ampl,
        detector_pol=new_detector_pol,
        dfoverf_per_mK=new_dfoverf_per_mK,
    )


def create_params_file_from_VNA_sweep(
    tile_name: str,
    min_resonance_frequency: float,
    max_resonance_frequency: float,
    min_distance_from_lo: float,
    res_freq: npt.NDArray,
    f_center: float,
    n_offres: int = 20,
    collision_threshold: float=1 / 2000.,
    isolated_resonance_threshold: float=1 / 1000.,
):
    """Create a tone list form a VNA sweep

    Arguments:
        res_freq (npt.NDArray): List of resonance frequencies identifed from the VNA.
        n_offres (int): Number of off-resonance tones to add. Defaults to 20.
        collision_threshold (float): Maximum fractional separation between collided resonances. Defaults to 
            1/2000.
        isolated_resonance_threshold (float): Minumum fractional for truly isolated 
            resonances. Defaults to 1/1000.

    """

    # Add offres tones to the list
    bb_freqs = res_freq[:] - f_center
    shift1 = bb_freqs - np.roll(bb_freqs,1)
    sort_gap = np.argsort(shift1[1:])
    offres_tones = 0.5 * (bb_freqs[sort_gap[-n_offres:]+1] + bb_freqs[sort_gap[-n_offres:]])
    chanmask = np.hstack((np.ones(np.size(bb_freqs)),np.zeros(np.size(offres_tones))))
    bb_freqs = np.hstack((bb_freqs,offres_tones))
    sort_ind = np.argsort(bb_freqs)
    chanmask = chanmask[sort_ind]
    bb_freqs = bb_freqs[sort_ind]

    #figure out which resonators are collided
    shift1 = bb_freqs - np.roll(bb_freqs,1)
    shift2 = np.roll(bb_freqs,-1) - bb_freqs
    nearest_res = np.minimum(abs(shift1), abs(shift2)) / bb_freqs
    collided_ind = np.argwhere(nearest_res < collision_threshold)
    non_isolated_ind = np.argwhere(nearest_res < isolated_resonance_threshold)

    #figure out which freqs are in the "approved" range
    valid_freqs = np.argwhere(
        min_resonance_frequency <= res_freq &
        max_resonance_frequency >= res_freq &
        min_distance_from_lo <= np.abs(res_freq - f_center)
    ).flatten()
    bb_valid = np.ndarray.flatten(bb_freqs[valid_freqs])

    chanmask = chanmask[valid_freqs]

    chanmask_non_collided = chanmask[:]
    chanmask_non_collided[collided_ind] = -1
    chanmask_isolated = chanmask[:]
    chanmask_isolated[non_isolated_ind] = -1

    initialize_params_file(
        tile_name,
        bb_valid,
        f_center
    )
    update_params_file(
        tile_name,
        chanmask=chanmask,
        chanmask_isolated=chanmask_isolated,
        chanmask_non_collided=chanmask_non_collided
    )


if __name__ == "__main__":
    # Be231102p2_tones = np.array([213078506, 214801178, 247405640, 255826241, 256855576, 260115494,
    #     263857108, 265547813, 269670205, 270298250, 272671603, 274710449,
    #     276383775, 278960930, 308519951, 312882861, 313150099, 314004392,
    #     314391462, 318555194, 322412444, 323717312, 326364689, 328323325,
    #     328705367, 335793390, 340651152, 368175878, 373470266, 375799889,
    #     375951626, 377837022, 384075676, 386531740, 386868808, 387216094,
    #     393636830, 397181500, 401249603, 404139304, 409101781, 417625771])

    params_file = 'params_tile_Device_aSi1_Channel2_telescope_275mK_20260420.h5'
    # with h5py.File(params_file, 'a') as params_fh:
    #     # params_fh.attrs['lo_freq'] = params_fh['lo_freq'][()]
    #     # del params_fh['lo_freq']
    #     params_fh['baseband_freqs'][:] = np.sort(params_fh['baseband_freqs'][:])
    add_off_resonance_tones(
        params_file,
        100,
        200e6,
        600e6,
        # q=1/100,
        # delta_offres_min=1e7,
    )

    # Be231102p2_LO_freq = 300e6
    # lo_freq = 4e8
    lo_freq = 4e8
    n_tones = 1000
    # baseband_freqs = np.concatenate([np.linspace(-246e6, -11e6, n_tones // 2), np.linspace(10e6, 245e6, n_tones // 2)])
    baseband_freqs = np.linspace(-220, 220, n_tones) * 1e6
    n_tones = np.size(baseband_freqs)
    tile_name = 'ONR_Blind_180_to_620MHz_1000_tones'
    # baseband_freqs = [450e6 - lo_freq]
    # tile_name = f'{n_tones}_tone_uniform_202050829'

    # Add 58 more tones
    # baseband_freqs = np.concatenate([
    #     Be231102p2_tones,
    #     np.linspace(218, 244, 27) * 1e6,
    #     np.linspace(344, 365, 22) * 1e6,
    #     np.linspace(284, 302, 9) * 1e6,
    # ])
    # sorted_indices = baseband_freqs.argsort()

    # baseband_freqs = baseband_freqs[sorted_indices] - lo_freq

    
    # tile_name = 'Be231102p2_100_tones'
    # tile_name = f'Device_aSi2_Channel3_{n_tones}_tones'
    # tile_name = 'Device_aSi1_Channel2_blind'
    # baseband_freqs = baseband_freqs - lo_freq
    # baseband_freqs =  np.load('/home/onrkids/readout/host/params/Default_tone_list.npy')

    #needs to be the same length as baseband
    # detdx = np.load('/home/onrkids/readout/host/params/detector_delta_x_tile2.npy')
    # detdy = np.load('/home/onrkids/readout/host/params/detector_delta_y_tile2.npy')
    # chanmask = np.load('/home/onrkids/onrkidpy/params/chanmask.npy')  #needs to be the same length as baseband_freqs, with 1 for the tones we keep and 0 the tones we remove
    # det_beam_ampl = np.load('/home/onrkids/readout/host/params/detector_beam_ampl_tile2.npy')
    # det_pol = np.load('/home/onrkids/readout/host/params/detector_pol_tile2.npy')
    # tone_powers = np.load('/home/onrkids/onrkidpy/params/Device_aSi1_Channel2_max_readout_power_dB.npy')
    # df_overf_per_mK = np.load('/home/onrkids/readout/host/params/dfoverf_per_mK_tile2.npy')
    detdx = detdy = chanmask = det_beam_ampl = det_pol = tone_powers = df_overf_per_mK = None
    # chanmask = np.zeros_like(baseband_freqs)
    # chanmask[np.where(sorted_indices < len(Be231102p2_tones))[0]] = 1


    initialize_params_file(tile_name, baseband_freqs, lo_freq, DEFAULT_PARAMS_DIRECTORY)
    update_params_file(
        tile_name,
        params_dir=DEFAULT_PARAMS_DIRECTORY,
        detector_delta_x=detdx,
        detector_delta_y=detdy,
        chanmask=chanmask,
        detector_beam_ampl=det_beam_ampl,
        detector_pol=det_pol,
        tone_powers=tone_powers,
        dfoverf_per_mK=df_overf_per_mK
    )
