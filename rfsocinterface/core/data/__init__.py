"""Submodule for data storage / processing related code."""

from rfsocinterface.core.data.data import (
    ProcessedData,
    DEFAULT_MAP_DPIX,
    N_POLARIZATION,
    DECIMATE_ORDER,
    BUTTER_ORDER,
    PsdBasis,
    flag_outliers,
    plot_map,
)
from rfsocinterface.core.data.routines import (
    ROUTINE_REGISTRY,
    register_routine,
    DataRoutine,
    ProcessingStage,
    CleanTOD,
    HighPassFilter,
    LowPassFilter,
    RemoveElectronicsNoise,
    BinTODIntoMap,
    PlotMap
)
# from rfsocinterface.core.data.map import (
#     BinTODIntoMap,
# )
from rfsocinterface.core.data.pipeline import Pipeline
from rfsocinterface.core.params import PARAM_FILE_N_TONE_ATTRIBUTES, initialize_params_file, update_params_file

ROUTINE_NAME_MAP = {
    'CleanTOD': CleanTOD,
    'HighPassFilter': HighPassFilter,
    'LowPassFilter': LowPassFilter,
    'RemoveElectronicsNoise': RemoveElectronicsNoise,
    # 'BinTODIntoMap': BinTODIntoMap,
}

__all__ = [
    ProcessedData,
    CleanTOD,
    HighPassFilter,
    LowPassFilter,
    RemoveElectronicsNoise,
    BinTODIntoMap,
    Pipeline,
    ProcessingStage,
    DataRoutine,
    PsdBasis,
    ROUTINE_REGISTRY,
    DEFAULT_MAP_DPIX,
    N_POLARIZATION,
    PARAM_FILE_N_TONE_ATTRIBUTES,
    DECIMATE_ORDER,
    BUTTER_ORDER,
    register_routine,
    initialize_params_file,
    update_params_file,
    flag_outliers,
    plot_map,
]