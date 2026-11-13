"""Progress-tracking related widgets."""

from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic
from typing import Protocol
from uuid import UUID

from PySide6.QtCore import QCoreApplication, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from rfsocinterface.core.tasks import (
    TERMINAL_STATUSES,
    CancellationPolicy,
    TaskManager,
    TaskRecord,
    TaskStatus,
)


class IncrementalProgressDialog(QProgressDialog):
    """QProgressDialog that increments its value by 1 at a time."""

    incremented = Signal()

    def __init__(self, *args, **kwargs):
        """Initialize an IncrementalProgressDialog."""
        super().__init__(*args, **kwargs)
        self.incremented.connect(self.increment)

    @Slot()
    def increment(self):
        """Increase the progress by 1."""
        self.setValue(self.value() + 1)


def make_progress_dialog_incrementer(pd: IncrementalProgressDialog) -> Callable:
    """Create a function that increments an IncrementalProgressDialog by 1."""

    def incrementer():
        pd.incremented.emit()
        QCoreApplication.processEvents()

    return incrementer


class ProgressData(Protocol):
    """Representation of a progress bar."""

    value: float | None
    minimum: float | None
    maximum: float | None
    label: str | None


def update_progress_bar(
    bar: QProgressBar,
    progress: ProgressData | None,
) -> None:
    """Updatea progress bar, distinguishing unknown progress from zero progress."""
    if progress is None or progress.value is None:
        bar.setRange(0, 0)  # Indeterminate
        return

    minimum = progress.minimum if progress.minimum is not None else 0
    maximum = progress.maximum if progress.maximum is not None else 1

    if maximum <= minimum:
        bar.setRange(0, 0)
        return

    fraction = (progress.value - minimum) / (maximum - minimum)
    fraction = max(0.0, min(1.0, fraction))

    bar.setRange(0, 1000)
    bar.setValue(round(fraction * 1000))


def format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f'{hours}:{minutes:02}:{seconds:02}'

    return f'{minutes:02}:{seconds:02}'


class SubtaskRow(QWidget):
    """Row for a subtask in the TaskProgressWidget."""

    def __init__(self, name: str, parent=None):
        """Initialize a SubtaskRow."""
        super().__init__(parent)

        self.name_label = QLabel(name)
        self.progress_label = QLabel()
        self.progress_label.setMinimumWidth(45)

        self.elapsed_label = QLabel()
        self.eta_label = QLabel()

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(7)

        header = QHBoxLayout()
        header.addWidget(self.name_label, 1)
        header.addWidget(self.progress_label)

        time_header = QHBoxLayout()
        time_header.addWidget(self.elapsed_label, 1)
        time_header.addWidget(self.eta_label, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(4)
        layout.addLayout(header)
        layout.addLayout(time_header)
        layout.addWidget(self.bar)

        self.set_pending()

    def set_pending(self):
        """Set the row to "pending"."""
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.progress_label.setText('Waiting')

    def update_elapsed(self, start_time: float):
        """Update the elapsed time for this subtask."""
        self.elapsed_label.setText(f'Elapsed time: {monotonic() - start_time:.2f} s')

    def update_eta(self, eta: float):
        """Update the ETA for this subtask."""
        self.eta_label.setText(f'Estimated time remaining: {eta:.2f} s')

    def update_progress(self, progress: ProgressData):
        """Update the progress for this subtask."""
        update_progress_bar(self.bar, progress)

        if progress.value is None:
            self.progress_label.setText('Running')
        elif self.bar.maximum() > 0:
            fraction = self.bar.value() / self.bar.maximum()
            self.progress_label.setText(f'{fraction:.0%}')
        else:
            self.progress_label.setText('Running')

        if progress.label:
            self.name_label.setToolTip(progress.label)


class TaskProgressWidget(QFrame):
    """Widget for representing progress of a Task and its subtasks."""

    def __init__(
        self,
        manager: TaskManager,
        task_id: UUID,
        parent=None,
    ):
        """Initialize a TaskProgressWidget."""
        super().__init__(parent)

        self.manager = manager
        self.task_id = task_id
        self.subtask_rows: dict[tuple[str, ...], SubtaskRow] = {}
        self.record: TaskRecord | None = None

        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.expand_button = QToolButton()
        self.expand_button.setArrowType(Qt.ArrowType.RightArrow)
        self.expand_button.setCheckable(True)
        self.expand_button.setVisible(False)
        self.expand_button.toggled.connect(self._toggle_details)

        self.title_label = QLabel()
        self.status_label = QLabel()

        self.elapsed_label = QLabel()
        self.eta_label = QLabel()

        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.clicked.connect(lambda: self.manager.cancel(self.task_id))

        header = QHBoxLayout()
        header.addWidget(self.expand_button)
        header.addWidget(self.title_label, 1)
        header.addWidget(self.status_label)
        header.addWidget(self.cancel_button)

        time_header = QHBoxLayout()
        time_header.addWidget(self.elapsed_label, 1)
        time_header.addWidget(self.eta_label, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)

        self.detail_label = QLabel()
        self.detail_label.setVisible(False)

        self.details = QWidget()
        self.details_layout = QVBoxLayout(self.details)
        self.details_layout.setContentsMargins(24, 0, 0, 0)
        self.details_layout.setSpacing(5)
        self.details.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addLayout(time_header)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.details)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_elapsed_times)
        self.timer.start()

    def _toggle_details(self, expanded: bool):
        self.details.setVisible(expanded)
        self.expand_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def _get_subtask_row(
        self,
        path: tuple[str, ...],
        display_name: str | None = None,
    ) -> SubtaskRow:
        if path not in self.subtask_rows:
            row = SubtaskRow(display_name or path[-1])
            self.subtask_rows[path] = row
            self.details_layout.addWidget(row)

        return self.subtask_rows[path]

    def update_elapsed_times(self):
        """Update the elapsed time for the task and all subtasks."""
        now = datetime.now(UTC).timestamp()

        record = self.record
        if record is None:
            return

        if record.start_time is not None:
            end = record.end_time if record.end_time is not None else now
            elapsed = max(0, end - record.start_time)

            self.elapsed_label.setText(f'Elapsed time: {format_duration(elapsed)}')

        for path, subtask in record.subtasks.items():
            if subtask.start_time is None:
                continue

            end = now if subtask.is_active else subtask.end_time

            elapsed = max(0, end - subtask.start_time)

            row = self.subtask_rows.get(path)

            if row is not None:
                row.elapsed_label.setText(f'Elapsed time: {format_duration(elapsed)}')

    def update_record(self, record: TaskRecord):
        """Update the widget to reflect the current state of the task."""
        if record.task.id != self.task_id:
            return
        self.record = record

        self.title_label.setText(record.task.name)
        self.status_label.setText(record.status.name.replace('_', ' ').title())

        # Set up subtask rows
        for path, subtask in record.subtasks.items():
            display_name = subtask.name
            self._get_subtask_row(path, display_name=display_name)

        # Overall progress
        update_progress_bar(self.progress_bar, record.progress)

        if record.status == TaskStatus.SUCCEEDED:
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(1000)

        elif record.status in TERMINAL_STATUSES:
            # Preserve partial progress on failure/cancellation.
            if record.progress is None:
                self.progress_bar.setRange(0, 1000)
                self.progress_bar.setValue(0)

        # Update elapsed time
        self.update_elapsed_times()

        # ETAs
        if record.eta is not None:
            self.eta_label.setText(f'Estimated time remaining: {record.eta:.2f} s')

        # Subtasks
        for path, subtask in record.subtasks.items():
            row = self._get_subtask_row(path)
            if subtask.progress is not None:
                row.update_progress(subtask.progress)
            if subtask.eta is not None:
                row.update_eta(subtask.eta)

        has_subtasks = bool(self.subtask_rows)
        self.expand_button.setVisible(has_subtasks)

        # Show a useful description of the latest reported subtask.
        if record.subtask_progress:
            latest = next(reversed(record.subtask_progress.values()))

            description = ' / '.join(latest.path)

            if latest.label:
                description += f' — {latest.label}'

            self.detail_label.setText(description)
            self.detail_label.setVisible(True)

        # Cancellation
        self.cancel_button.setEnabled(
            record.status not in TERMINAL_STATUSES
            and record.status != TaskStatus.CANCELLING
            and record.task.cancellation_policy != CancellationPolicy.DISABLED
        )

        if record.status == TaskStatus.CANCELLING:
            self.cancel_button.setText('Cancelling…')
        else:
            self.cancel_button.setText('Cancel')

        # Display errors without losing the progress history.
        if record.status == TaskStatus.FAILED and record.error:
            self.status_label.setToolTip(record.error)
        else:
            self.status_label.setToolTip('')
