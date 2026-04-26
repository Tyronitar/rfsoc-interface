"""Handle RFSoC Parameter Files"""

import inspect
import logging
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pdb
import tables

from rfsocinterface.core.utils import DEFAULT_PARAMS_DIRECTORY, PERMISSIONS_ALL_FULL, get_params_file_template, pad_to_length


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
    with tables.open_file(params_tile_file, 'w') as params_fh:
        params_fh.root._v_attrs.n_tones = n_tones
        params_fh.root._v_attrs.tile_name = tile_name
        params_fh.root._v_attrs.tile_number = 0
        params_fh.root._v_attrs.chan_number = 0
        params_fh.root._v_attrs.ifslice_number = 0
        chanmask = params_fh.create_array(
            '/',
            'chanmask',
            atom=tables.Int8Atom(),
            shape=(n_tones,),
        )
        chanmask[:] = 1
        chanmask_non_collided = params_fh.create_array(
            '/',
            'chanmask_non_collided',
            atom=tables.Int8Atom(),
            shape=(n_tones,),
        )
        chanmask_non_collided[:] = 1
        chanmask_isolated = params_fh.create_array(
            '/',
            'chanmask_isolated',
            atom=tables.Int8Atom(),
            shape=(n_tones,),
        )
        chanmask_isolated[:] = 1
        params_fh.create_array(
            '/',
            'baseband_freqs',
            obj=baseband_freqs,
        )
        params_fh.create_array(
            '/',
            'tone_powers',
            obj=np.ones(n_tones, dtype=np.float32),
        )
        params_fh.create_array(
            '/',
            'lo_freq',
            obj=lo_freq,
        )
        params_fh.create_array(
            '/',
            'detector_delta_x',
            atom=tables.Float32Atom(),
            shape=(n_tones,),
        )
        params_fh.create_array(
            '/',
            'detector_delta_y',
            atom=tables.Float32Atom(),
            shape=(n_tones,),
        )
        det_beam_ampl = params_fh.create_array(
            '/',
            'detector_beam_ampl',
            atom=tables.Float32Atom(),
            shape=(n_tones,),
        )
        det_beam_ampl[:] = 1
        det_pol = params_fh.create_array(
            '/',
            'detector_pol',
            atom=tables.Int8Atom(),
            shape=(n_tones,),
        )
        det_pol[:] = 1
        dfoveref_per_mK = params_fh.create_array(
            '/',
            'dfoverf_per_mK',
            atom=tables.Float64Atom(),
            shape=(n_tones,),
        )
        dfoveref_per_mK[:] = 1
    _logger.info(f'Initialized params file {params_tile_file}')

def update_params_file(
    tile_name: str,
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
    params_tile_file = Path(get_params_file_template(tile_name, params_dir=params_dir))
    if not params_tile_file.exists():
        raise FileExistsError(f'Params file {params_tile_file} does not exist')

    signature = inspect.signature(update_params_file)
    keyword_args = {
        param.name: param.default
        for param in signature.parameters.values()
        if param.default is not inspect.Parameter.empty
    }

    with tables.open_file(params_tile_file, 'a') as fh:
        for k in keyword_args:  # Check all of the keyword arguments
            if k == 'params_dir':
                continue  # We only care about the parameters
            v = locals()[k]
            if v is None:
                continue  # The value is not being updated, so skip it
            # Check the array is the correct size if needed
            if k in PARAM_FILE_N_TONE_ATTRIBUTES:
                if np.size(v) != fh.root._v_attrs.n_tones:
                    raise ValueError(
                        f'{k} size {np.size(v)} does not match n_tones {fh.root._v_attrs.n_tones}'
                    )
            fh.get_node('/', k)[:] = v

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
    #Be231102p2_tones = np.array([213078506, 214801178, 247405640, 255826241, 256855576, 260115494,
    #     263857108, 265547813, 269670205, 270298250, 272671603, 274710449,
    #     276383775, 278960930, 308519951, 312882861, 313150099, 314004392,
    #     314391462, 318555194, 322412444, 323717312, 326364689, 328323325,
    #     328705367, 335793390, 340651152, 368175878, 373470266, 375799889,
    #     375951626, 377837022, 384075676, 386531740, 386868808, 387216094,
    #     393636830, 397181500, 401249603, 404139304, 409101781, 417625771])

    Be260114Tr_tones_1 = np.array([170000000,173585000, 211857500, 216760000, 217702500, 218967500, 232777500,
    254320000, 260177500, 273445000, 282582500, 286537500, 304115000,
    312987500, 316692500, 320352500, 323742500, 324141000, 327667500, 337145000,
    340375000, 357022500, 358847500, 413091000,429853000, 449282500, 492040000, 502837500,
    507970000,615725000, 645211000])
    Be260114Tr_tones_2 = np.array([ 672578500, 703408500, 727816000, 737451000,
    810936000, 879973500, 1035102000, 1038294500, 1057924500, 1092882000,
    1126594500, 1148194500, 1154394500])
    Be260114Tr_tones_3 = np.array([1170000000, 1180667000, 1189129500, 1190174500,
    1221847000, 1232217000, 1246642000, 1266664500, 1296274500, 1321964500,
    1322962000, 1340739500, 1379649500, 1395659500, 1398229500, 1427789500,
    1452124500, 1463652000, 1511963252, 1529370290, 1534427740, 1561959479,
    1570283199, 1657808451])




    LO_freq = 420e6
    # lo_freq = 4e8
    #lo_freq = 4e8
    n_tones = 1
    # baseband_freqs = np.concatenate([np.linspace(-246e6, -11e6, n_tones // 2), np.linspace(10e6, 245e6, n_tones // 2)])
    #baseband_freqs = np.arange(-200e6, 200e6 + 1, 400e3)
    #n_tones = np.size(baseband_freqs)
    # baseband_freqs = [450e6 - lo_freq]
    # tile_name = f'{n_tones}_tone_uniform_202050829'
        # Add 58 more tones
    target_n_tones = 1000
    new_tones = Be260114Tr_tones_1.copy()
    while len(new_tones) < target_n_tones:
        sorted_tones = np.sort(new_tones)
        gaps = np.diff(sorted_tones)
        max_gap_idx = np.argmax(gaps)
        print(gaps[max_gap_idx])
        
        # Add a tone in the middle of the largest gap
        new_tone = (sorted_tones[max_gap_idx] + sorted_tones[max_gap_idx + 1]) / 2
        new_tones = np.append(new_tones, new_tone)
    new_tones = np.sort(new_tones)

    original_tone_indices = [i for i, t in enumerate(new_tones) if t in Be260114Tr_tones_1]
    print(f"Original tones in new list: {original_tone_indices}")
    baseband_freqs = np.array(new_tones) - LO_freq


    # sorted_indices = baseband_freqs.argsort()

    # baseband_freqs = baseband_freqs[sorted_indices] - lo_freq
    
    
    tile_name = 'Be260114Tr_1000_tones_1'
    #tile_name = f'Device_aSi2_Channel3_{n_tones}_tones'
    # tile_name = 'Device_aSi1_Channel2_blind'
    # baseband_freqs = baseband_freqs - lo_freq
    # baseband_freqs =  np.load('/home/onrkids/readout/host/params/Default_tone_list.npy')

    #needs to be the same length as baseband
    # detdx = np.load('/home/onrkids/readout/host/params/detector_delta_x_tile2.npy')
    # detdy = np.load('/home/onrkids/readout/host/params/detector_delta_y_tile2.npy')
    # chanmask = np.load('/home/onrkids/onrkidpy/params/chanmask.npy')  #needs to be the same length as baseband_freqs, with 1 for the tones we keep and 0 the tones we remove
    # det_beam_ampl = np.load('/home/onrkids/readout/host/params/detector_beam_ampl_tile2.npy')
    # det_pol = np.load('/home/onrkids/readout/host/params/detector_pol_tile2.npy')
    #pdb.set_trace()
    # df_overf_per_mK = np.load('/home/onrkids/readout/host/params/dfoverf_per_mK_tile2.npy')
    detdx = detdy = chanmask = det_beam_ampl = det_pol = tone_powers = df_overf_per_mK = None
    #tone_powers = np.load('max_readout_power_simon_manual_adjusted.npy')

    chanmask = np.zeros_like(baseband_freqs)
    chanmask[original_tone_indices] = 1
    chanmask[0] = 0
    baseband_freqs_sorted_idx = np.argsort(baseband_freqs)
    baseband_freqs = baseband_freqs[baseband_freqs_sorted_idx]
    chanmask = chanmask[baseband_freqs_sorted_idx]
    print(chanmask)
    print(tone_powers)
    offres_ind = np.where(chanmask ==0)


    initialize_params_file(tile_name, baseband_freqs, LO_freq, DEFAULT_PARAMS_DIRECTORY)
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
