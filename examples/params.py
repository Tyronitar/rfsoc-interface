import logging

import numpy as np

from rfsocinterface.core.params import RFSoCParameters
import pdb
_logger = logging.getLogger(__name__)


def db_to_power_ratio(db: np.ndarray) -> np.ndarray:
    """Convert a dB power change into a linear power ratio."""
    return 10 ** (np.asarray(db, dtype=float) / 10.0)


def balance_tone_powers_with_offres_budget(
    delta_db: np.ndarray,
    onres_ind: np.ndarray,
    offres_ind: np.ndarray,
    total_power: float | None = None,
) -> tuple[np.ndarray, float]:
    """
    Convert per-tone dB changes (relative to a flat baseline of power=1 per
    tone) into fractional tone powers, using the off-resonance tones to
    absorb whatever power is left so the firmware's automatic total-power
    renormalization ends up being a no-op — meaning the dB change actually
    applied to each on-resonance tone matches `delta_db` exactly.

    If the on-resonance tones alone need more power than `total_power`
    allows (even with off-res tones at 0), the shortfall is instead handed
    back as `extra_attenuation_db`: the amount of *additional* attenuation
    to dial in on the variable attenuator so the physical output power
    stays where it was, while every on-resonance tone still gets exactly
    its requested relative dB change.

    Parameters
    ----------
    delta_db    : dB change for every tone. Only entries at onres_ind are
                  used; offres_ind entries are ignored and overwritten.
    onres_ind   : indices of on-resonance tones.
    offres_ind  : indices of off-resonance tones (free to set).
    total_power : target total power to conserve. Defaults to the total
                  number of tones (i.e. assumes every tone started at a
                  fractional power of 1 before this change).

    Returns
    -------
    tone_powers_frac    : fractional power for every tone.
    extra_attenuation_db: additional attenuation (dB) needed downstream to
                          keep physical output power constant. 0.0 if the
                          off-resonance tones had enough budget on their own.
    """
    delta_db = np.asarray(delta_db, dtype=float)
    n_tones  = len(delta_db)
    n_offres = len(offres_ind)

    if total_power is None:
        total_power = float(n_tones)

    tone_powers_frac = np.zeros(n_tones)
    tone_powers_frac[onres_ind] = db_to_power_ratio(delta_db[onres_ind])

    onres_total   = tone_powers_frac[onres_ind].sum()
    offres_budget = total_power - onres_total

    if offres_budget >= 0:
        if n_offres > 0:
            tone_powers_frac[offres_ind] = offres_budget / n_offres
        elif offres_budget > 1e-9:
            _logger.warning(
                f"No off-resonance tones available to absorb "
                f"{offres_budget:.6g} of leftover power budget; total "
                f"power won't be exactly conserved."
            )
        return tone_powers_frac, 0.0

    # On-res tones alone exceed the budget — off-res tones can't help
    # (already floored at 0), so push the overshoot onto the attenuator
    # instead of clipping anyone's requested dB change.
    tone_powers_frac[offres_ind] = 0.0
    extra_attenuation_db = 10 * np.log10(onres_total / total_power)
    _logger.info(
        f"On-resonance tones need {onres_total:.6g} of power vs a budget of "
        f"{total_power:.6g}; dialing in {extra_attenuation_db:.3f} dB of "
        f"extra attenuation to compensate instead of altering requested "
        f"tone powers."
    )
    return tone_powers_frac, extra_attenuation_db


if __name__ == '__main__':


    filename = '/data/params/params_tile_Be260114BL_1000_tones_2.h5'
    params = RFSoCParameters(filename)

    onres_ind      = params.onres_ind
    offres_ind     = params.offres_ind
    bb_freqs_onres = params.baseband_freqs[onres_ind]




    f_center = 5.775e8

    onres_tones = np.array([353.022, 410.37,415.43, 440.99, 492.09, 493.177, 505.869,527.28, 605.495, 608.65, 626.461,646.21169,646.844, 724.273 , 750.330, 767.65,800.259  ])*1e6
   
    bb_freqs_onres = onres_tones-f_center
    new_params = RFSoCParameters.new_file(
        'FTS_Tone_List_Be260114BL_tones_260729', len(bb_freqs_onres), f_center=f_center
    )
    new_params.baseband_freqs[:] = bb_freqs_onres
    new_params.rfin  = 15
    new_params.rfout = 15 
    new_params.add_off_resonance_tones_greedy(
        new_tile_name='FTS_Tone_List_Be260114BL_100_tones_260729',
        n_offres=100 - len(bb_freqs_onres),
        f_min=3.5e8,
        f_max=8.0e8,
        q=1/1000.,
        delta_offres_min=1e6,
        tone_powers_frac = np.ones(100)
    )