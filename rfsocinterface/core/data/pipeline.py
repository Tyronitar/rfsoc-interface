"""Module for code related to data processing pipelines."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal, overload

from rfsocinterface.core.data.routines import (
    ROUTINE_REGISTRY,
    DataRoutine,
    RoutineResult,
)
from rfsocinterface.core.data.storage import ConsolidatedData, ProcessedData
from rfsocinterface.core.data.utils import AZ_BACKLASH_DEG
from rfsocinterface.core.tasks import (
    Task,
    TaskCancelled,
    TaskContext,
    TaskProgress,
)
from rfsocinterface.core.utils import nullcontext

_logger = logging.getLogger(__name__)


class Pipeline:
    """Class representing a data pipeline."""

    def __init__(self, routines: Sequence[DataRoutine] | None = None):
        """Initialize a Pipeline."""
        if routines is None:
            routines = []
        self.routines = routines
        self._context = None
        self._task_progress = None
        self._current_step = 0

    def from_tod(
        self,
        date: str,
        setnum: int,
        downsampling_factor: int = 1,
        use_pps: bool = True,
        az_backlash: float = AZ_BACKLASH_DEG,
        za_backlash: float = 0.0,
        close_file: bool = False,
        context: TaskContext | None = None,
    ) -> tuple[ProcessedData, tuple[RoutineResult | tuple[RoutineResult, ...], ...]]:
        """Run a pipeline starting from the TOD files for the desired data set."""
        # Setup context
        if context is not None:
            self._setup_task_context(context, start='consolidated')

        _logger.info(f'Pipeline: Running pipeline on TOD {date}_set{setnum}')

        # Create ConsolidatedData
        try:
            with self._get_next_subtask_context_manager() as subcontext:
                _logger.info('Pipeline: Creating consolidated data...')
                cd = ConsolidatedData.from_tod(
                    date,
                    setnum,
                    downsampling_factor=downsampling_factor,
                    use_pps=use_pps,
                    az_backlash=az_backlash,
                    za_backlash=za_backlash,
                    context=subcontext,
                )
        except TaskCancelled:
            _logger.info('Pipeline: Pipeline execution was cancelled.')
            raise
        except BaseException:
            _logger.exception(
                'Pipeline: Error encountered during consolidated data creation.'
            )
            raise

        # Create ProcessedData
        try:
            with self._get_next_subtask_context_manager() as subcontext:
                _logger.info('Pipeline: Creating processed data...')
                pd = cd.create_processed_data(context=subcontext)
        except TaskCancelled:
            _logger.info('Pipeline: Pipeline execution was cancelled.')
            raise
        except BaseException:
            _logger.exception(
                'Pipeline: Error encountered during processed data creation.'
            )
            raise
        finally:
            cd.close()

        try:
            results = self.run(pd, context=context)
        except TaskCancelled:
            _logger.info('Pipeline: Pipeline execution was cancelled.')
            pd.close()
            raise
        except BaseException:
            _logger.warning(
                f'Pipeline: Closing {pd} in response to error.'
            )
            pd.close()
            raise

        if close_file:
            # Close the file after we're done
            pd.close()
        return pd, results

    def from_consolidated_data(
        self,
        date: str,
        setnum: int,
        close_file: bool = False,
        context: TaskContext | None = None,
    ) -> tuple[ProcessedData, tuple[RoutineResult | tuple[RoutineResult, ...], ...]]:
        """Run a pipeline starting from a consolidated file."""
        if context is not None:
            self._setup_task_context(context, start='processed')
        _logger.info(
            f'Pipeline: Running pipeline from ConsolidatedData {date}_set{setnum}'
        )
        cd = ConsolidatedData.load(date, setnum)
        try:
            with self._get_next_subtask_context_manager() as subcontext:
                _logger.info('Pipeline: Creating processed data...')
                pd = cd.create_processed_data(context=subcontext)
        except TaskCancelled:
            _logger.info('Pipeline: Pipeline execution was cancelled.')
            raise
        except BaseException:
            _logger.exception(
                'Pipeline: Error encountered during processed data creation.'
            )
            raise
        finally:
            cd.close()

        try:
            results = self.run(pd, context=context)
        except TaskCancelled:
            _logger.info('Pipeline: Pipeline execution was cancelled.')
            pd.close()
            raise
        except BaseException:
            _logger.warning(
                f'Pipeline: Closing {pd} in response to error.'
            )
            pd.close()
            raise

        if close_file:
            # Close the file after we're done
            pd.close()
        return pd, results

    def run(
        self,
        *pdata: ProcessedData,
        context: TaskContext | None = None,
    ) -> tuple[RoutineResult | tuple[RoutineResult, ...], ...]:
        """Run this pipeline on one or more processed data objects."""
        if not pdata:
            raise ValueError('Pipeline requires at least one ProcessedData object.')
        self.validate(len(pdata))

        # Don't reset context if this was called in `from_consolidated_data`
        # or `from_tod`. `self._task_progress`` is only None if this is the beginning of
        # the pipeline's execution.
        if context is not None and self._task_progress is None:
            self._setup_task_context()
        results = []

        try:
            for routine in self.routines:
                with self._get_next_subtask_context_manager() as subcontext:
                    results.append(routine.apply(*pdata, context=subcontext))
        except TaskCancelled:
            msg = 'Pipeline: Pipeline execution was cancelled.'
            _logger.info(msg)
            raise
        except BaseException:
            msg = 'Pipeline: Error encountered during pipeline execution.'
            _logger.exception(msg)
            raise
        else:
            return tuple(results)
        finally:
            self._clean_task_context()

    @overload
    def add_routine(self, name: str, **params):
        pass

    @overload
    def add_routine(self, routine_cls: type[DataRoutine], **params):
        pass

    @overload
    def add_routine(self, routine: DataRoutine):
        pass

    def add_routine(self, arg: str | type[DataRoutine] | DataRoutine, **params):
        """Instatiate a DataRoutine and add it to this pipeline.

        Raises:
            (KeyError): If the `name` is not registered in the ROUTINE_REGISTRY.

        """
        if isinstance(arg, str):
            routine_cls = ROUTINE_REGISTRY[arg]
            routine = routine_cls(**params)
        elif isinstance(arg, type):
            routine = arg(**params)
        else:
            routine = arg
        self.routines.append(routine)
        _logger.debug(
            f'Pipeline: Added routine {routine.__class__.__name__} with '
            f'params {params} to pipeline.'
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

    def create_task(self) -> Task:
        """Create a task for executing the pipeline."""

    def _setup_task_context(
        self,
        context: TaskContext,
        start: Literal['consolidated', 'processed', 'routines'],
    ):
        """Create the TaskContext for running this pipeline."""
        # self._task_progress = TaskProgress(
        #     context,
        #     subtasks=[
        #         (routine.name, 1.0) for routine in self.routines
        #     ]
        # )
        self._context = context
        subtasks = []
        if start.lower() == 'consolidated':
            subtasks.append(('Create ConsolidatedData', 1.0))
            subtasks.append(('Create ProcessedData', 1.0))
        elif start.lower() == 'processed':
            subtasks.append(('Create ProcessedData', 1.0))
        self._task_progress = TaskProgress(
            context,
            subtasks=subtasks + [(routine.name, 1.0) for routine in self.routines],
        )
        self._current_step = 0

    def _clean_task_context(self):
        """Cleanup the task context after completing a run."""
        self._context = None
        self._task_progress = None
        self._current_step = 0

    def _get_next_subtask_context_manager(self):
        """Return a context manager for the next task."""
        if self._context is not None:
            # Check for cancellation first:
            self._context.check_cancelled()
            cm = self._task_progress.subtask(self._current_step)
        else:
            cm = nullcontext(None)
        self._current_step += 1
        return cm
