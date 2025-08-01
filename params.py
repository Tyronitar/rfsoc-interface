from pathlib import Path
import pdb

import numpy as np
import tables

from rfsocinterface.core.data.data import initialize_params_file, update_params_file, DATA_DIRECTORY
from rfsocinterface.core.rfsoc import RFSOCWrapper



if __name__ == "__main__":
    tile_name = 'thousand_tone_uniform_20250801'
    lo_freq = 4e8
    baseband_freqs = np.linspace(10, 210, 1000) * 1e6
    params_dir = Path(DATA_DIRECTORY) / 'params'
    params_dir.mkdir(parents=True, exist_ok=True)

    initialize_params_file(tile_name, baseband_freqs, lo_freq, params_dir)
    fh = tables.open_file(params_dir / f'params_tile_{tile_name}.h5', 'r')
    pdb.set_trace()