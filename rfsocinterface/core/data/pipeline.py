"""Module for code related to data processing pipelines."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from rfsocinterface.core.data.routines import ROUTINE_REGISTRY, DataRoutine
from rfsocinterface.core.data.storage import ConsolidatedData, ProcessedData

_logger = logging.getLogger(__name__)


class Pipeline:
    """Class representing a data pipeline."""

    def __init__(self, routines: Sequence[DataRoutine] = []):
        """Initialize a Pipeline."""
        self.routines = routines

    def from_tod(
        self, date: str, setnum: int, downsampling_factor: int = 1, use_pps: bool = True
    ) -> ProcessedData:
        """Run a pipeline starting from the TOD files."""
        _logger.info(f'Pipeline: Running pipeline on TOD {date}_set{setnum}')
        cd = ConsolidatedData.from_tod(
            date, setnum, downsampling_factor=downsampling_factor, use_pps=use_pps
        )
        _logger.info('Pipeline: Creating processed data...')
        pd = cd.create_processed_data()
        self.run(pd)
        return pd

    def from_consolidated_data(self, date: str, setnum: int) -> ProcessedData:
        """Run a pipeline starting from the consolidated file."""
        _logger.info(
            f'Pipeline: Running pipeline from ConsolidatedData {date}_set{setnum}'
        )
        cd = ConsolidatedData.load(date, setnum)
        _logger.info('Pipeline: Creating processed data...')
        pd = cd.create_processed_data()
        self.run(pd)
        return pd

    def add_routine(self, name: str, **params):
        """Instatiate a DataRoutine and add it to this pipeline.

        Raises:
            (KeyError): If the `name` is not registered in the ROUTINE_REGISTRY.

        """
        routine_cls = ROUTINE_REGISTRY[name]
        routine = routine_cls(**params)
        self.routines.append(routine)
        _logger.debug(
            f'Pipeline: Added routine {name} with params {params} to pipeline.'
        )

    def load_config(self, config: dict):
        """Loads a pipeline configuration from a dictionary.

        The dictionary should have the following format:
        {
            "routine_name_1": {
                "param1": value1,
                "param2": value2,
                ...
            },
            "routine_name_2": {
                "param1": value1,
                "param2": value2,
                ...
            },
            ...
        }
        """
        for name, params in config.items():
            self.add_routine(name, **params)

    def validate(self, n_inputs: int) -> None:
        """Validates the number of inputs for all routines."""
        for routine in self.routines:
            count = 1 if routine.map_over_inputs else n_inputs
            routine.validate_input_count(count)

    def run(self, *pdata: ProcessedData):
        """Run this pipeline on processed data objects."""
        if not pdata:
            raise ValueError('Pipeline requires at least one ProcessedData object.')
        self.validate(len(pdata))

        for routine in self.routines:
            routine.apply(*pdata)
