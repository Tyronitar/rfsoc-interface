import pdb
import logging
import logging.config
from uuid import UUID

import matplotlib.pyplot as plt
import numpy as np

from rfsocinterface.core.data import (
    ConsolidatedData,
    ProcessedData,
    Pipeline,
    CleanTOD,
    RemoveElectronicsNoise,
    HighPassFilter,
    LowPassFilter,
    BinTODIntoMap,
    PlotMap,
    BinTODIntoVideo,
    AnimateVideo,
)
from rfsocinterface.analysis import (
    ComputeNoisePSD,
    PlotPSD,
    PsdBasis,
    AnalyzeBeamMap,
    PlotBeamMap,
    CheckFocus,
)
from rfsocinterface.core.params import RFSoCParameters, DEFAULT_DFOVERF_PER_MK

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


from rfsocinterface.core.tasks import (
    MultiprocessingBackend,
    ThreadingBackend,
    TaskManager,
    TaskRecord,
    TaskProgress,
    CancellationPolicy,
    Task,
    TaskStatus,
)
from rfsocinterface.gui.widgets import TaskProgressWidget

class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Background task demo')
        self.resize(750, 350)
        self.manager = TaskManager(ThreadingBackend(0.25))
        self.rows: dict[UUID, TaskProgressWidget] = {}
        layout = QVBoxLayout(self)
        self.add_button = QPushButton('Start pipeline')
        # add_button.clicked.connect(self.create_task)
        layout.addWidget(self.add_button)
        self.tasks_layout = QVBoxLayout()
        layout.addLayout(self.tasks_layout)
        layout.addStretch()
        self.manager.changed.connect(self.on_changed)
        self.manager.event_received.connect(self.on_event)

    def create_task(self, pipeline: Pipeline, date: str, setnum: int, **kwargs):
        kwargs['make_pickle_safe'] = True
        task = Task(
            pipeline.from_tod,
            args=(date, setnum),
            kwargs=kwargs,
            name=f'Pipeline Execution on {date}_set{setnum}',
            with_context=True,
            cancellation_policy=CancellationPolicy.COOPERATIVE,
            resources=frozenset({f'{date}_set{setnum}'}),
        )
        self.add_task(task)

    def add_task(self, task: Task):
        row = TaskProgressWidget(self.manager, task.id, parent=self)
        self.rows[task.id] = row
        self.tasks_layout.addWidget(row)
        self.manager.submit(task)

    def on_changed(self, record: TaskRecord):
        row = self.rows.get(record.task.id)
        if row is not None:
            if record.status == TaskStatus.FAILED:
                print(f'Task failed: {record.error}\n{record.traceback}')
            row.update_record(record)

    def on_event(self, event):
        if event.kind == 'plot_request':
            print('Received plot request:', event.payload)
            # Construct a matplotlib FigureCanvasQTAgg here in the GUI thread.
        elif event.kind == 'plot':
            # dialog = show_figure(event.data, parent=main_window)

            # Retain a reference so the dialog stays alive.
            # main_window.plot_dialogs.append(dialog)
            ...

    def closeEvent(self, event):
        self.manager.close()
        self.manager.runner.wait()
        super().closeEvent(event)




if __name__ == '__main__':
    logging.config.fileConfig('rfsocinterface/logging.conf')
    _logger = logging.getLogger('rfsocinterface')
    _logger.handlers[0].setLevel(logging.INFO)

    lp_filter_freq = 15
    hp_filter_freq = 0.03

    ds_factor = 1

    dataset = 'data_freq'
    datasets = ['.*/data_freq_diss']

    check_focus = CheckFocus(
        'az',
        [170],
        dataset=dataset,
    )

    lp_filter = LowPassFilter(filter_freq=lp_filter_freq, datasets=datasets)
    hp_filter = HighPassFilter(filter_freq=hp_filter_freq, datasets=datasets)
    clean_tod = CleanTOD(dataset=dataset)
    bin_tod_to_map = BinTODIntoMap(
        hp_filter_freq=hp_filter_freq,
        lp_filter_freq=lp_filter_freq,
        beam_map_mode=True,
        dataset=dataset,
        az_trim=0,
        za_trim=0,
        dpix=0.03,
        r0=0.0,
    )
    plot_map_routine = PlotMap(
        show=True,
        # max_abs_threshold=0.4,
        keep_figure_open=False,
        channel=None,
        # show_optical_overlay=True,
        # vmin=-400,
        # vmax=400,
        overwrite=True,
        )

    pipeline = Pipeline([
        hp_filter,
        lp_filter,
        # clean_tod,
        # bin_tod_to_map,
        # plot_map_routine,
    ])

    date = '20260820'  # For testing normal maps
    setnum = 1005
    # date = '20260710'  # For testing beammaps
    # setnum = 1006
    # date = '20260917'  # For testing video
    # setnum = 1007
    # date = '20261001'  # For testing normal maps
    # setnum = 1006

    # date = '20260917'
    # setnum = 1005


    app = QApplication()
    win = Window()
    win.add_button.clicked.connect(
        lambda: win.create_task(pipeline, date, setnum, downsampling_factor=ds_factor))

    win.show()
    app.exec()

    # pdata, _ = pipeline.from_tod(date, setnum, ds_factor, use_pps=True)
    # pdata, _ = pipeline.from_consolidated_data(date, setnum)
    # cdata = ConsolidatedData.load(date, setnum)
    # pdata = ProcessedData.load(date, setnum)
    # pdb.set_trace()

    # bin_tod_to_map.apply(pdata)
    # plot_map_routine.apply(pdata)
    # plot_map_routine = PlotMap(
    #     show=True,
    #     # max_abs_threshold=0.4,
    #     channel=1,
    #     # show_optical_overlay=True,
    #     vmin=-500,
    #     vmax=500,
    #     overwrite=False,
    # )
    # plot_map_routine.apply(pdata)
    # pdb.set_trace()
