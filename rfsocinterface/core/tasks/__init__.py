"""Subpackage for handling the execution of tasks in the background."""

from rfsocinterface.core.tasks.backend import (
    BackendUpdate,
    MultiprocessingBackend,
    MultiprocessingWorkerHandle,
    ReceiverStatus,
    ReceiverUpdate,
    TaskBackend,
    WorkerExit,
)
from rfsocinterface.core.tasks.context import (
    SubtaskContext,
    TaskContext,
    TaskProgress,
)
from rfsocinterface.core.tasks.manager import (
    TaskManager,
    TaskRecord,
)
from rfsocinterface.core.tasks.runner import (
    BackendCommand,
    BackendCommandType,
    BackendRunner,
)
from rfsocinterface.core.tasks.task import (
    TERMINAL_STATUSES,
    CancellationPolicy,
    Cancelled,
    Failed,
    IPCFailed,
    Message,
    Progress,
    Started,
    SubtaskProgress,
    SubtasksDefined,
    Succeeded,
    Task,
    TaskCancelled,
    TaskEvent,
    TaskStatus,
    TerminalEvent,
)

__all__ = [
    'TERMINAL_STATUSES',
    'BackendCommand',
    'BackendCommandType',
    'BackendRunner',
    'BackendUpdate',
    'CancellationPolicy',
    'Cancelled',
    'Failed',
    'IPCFailed',
    'Message',
    'MultiprocessingBackend',
    'MultiprocessingWorkerHandle',
    'Progress',
    'ReceiverStatus',
    'ReceiverUpdate',
    'Started',
    'SubtaskContext',
    'SubtaskProgress',
    'SubtasksDefined',
    'Succeeded',
    'Task',
    'TaskBackend',
    'TaskCancelled',
    'TaskContext',
    'TaskEvent',
    'TaskManager',
    'TaskProgress',
    'TaskRecord',
    'TaskStatus',
    'TerminalEvent',
    'WorkerExit',
]
