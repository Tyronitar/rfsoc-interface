"""Submodule for data storage / processing related code."""

from rfsocinterface.core.data.data import (
    ProcessedData,
    ProcessedDataL0,
    ProcessedDataL1,
    ProcessedDataLN,
    MapData,
    DEFAULT_MAP_DPIX,
    N_POLARIZATION,
    DECIMATE_ORDER,
    BUTTER_ORDER,
    flag_outliers,
    plot_map,
)
from rfsocinterface.core.data.routines import (
    DataRoutine,
    ProcessingStage,
    Downsample,
    CleanTOD,
    HighPassFilter,
    LowPassFilter,
    GaussianFilter,
    RemoveElectronicsNoise,
    PsdBasis,
    ComputeNoisePSD
)
from rfsocinterface.core.data.map import (
    BinTODIntoMap,
)
from rfsocinterface.core.data.pipeline import DataPipeline, RoutineApplier
from rfsocinterface.core.params import PARAM_FILE_N_TONE_ATTRIBUTES, initialize_params_file, update_params_file

ROUTINE_NAME_MAP = {
    'Downsample': Downsample,
    'CleanTOD': CleanTOD,
    'HighPassFilter': HighPassFilter,
    'LowPassFilter': LowPassFilter,
    'GaussianFilter': GaussianFilter,
    'RemoveElectronicsNoise': RemoveElectronicsNoise,
    'BinTODIntoMap': BinTODIntoMap,
}

__all__ = [
    ProcessedData,
    ProcessedDataL0,
    ProcessedDataL1,
    ProcessedDataLN,
    MapData,
    Downsample,
    CleanTOD,
    ComputeNoisePSD,
    HighPassFilter,
    LowPassFilter,
    GaussianFilter,
    RemoveElectronicsNoise,
    BinTODIntoMap,
    DataPipeline,
    RoutineApplier,
    ProcessingStage,
    DataRoutine,
    PsdBasis,
    DEFAULT_MAP_DPIX,
    N_POLARIZATION,
    PARAM_FILE_N_TONE_ATTRIBUTES,
    DECIMATE_ORDER,
    BUTTER_ORDER,
    initialize_params_file,
    update_params_file,
    flag_outliers,
    plot_map,
]