"""
Utilities for building concurrent PyQt5 applications.
"""

from __future__ import absolute_import

import threading
import weakref
import logging
import warnings
import concurrent.futures

from PySide6.QtCore import (
    Qt, QObject, Q_ARG, QMetaObject, QThread, QThreadPool, QRunnable, QEvent,
    QCoreApplication, Signal, Slot
)
from PySide6.QtWidgets import QApplication


def method_invoke(method, sig, conntype=Qt.QueuedConnection):
    """
    Return a callable to invoke the QObject's method.

    This wrapper can be used to invoke/call a method across thread
    boundaries.

    NOTE
    ----
    An event loop MUST be running in the target QObject's thread.

    Parameters
    ----------
    method : boundmethod
        A bound method of a QObject registered with the QObject meta system
        (decorated by a Slot or Signature decorators)
    sig : Tuple[type]
        A tuple of positional argument types.
    conntype: Qt.ConnectionType
        The connection/call type (Qt.QueuedConnection and
        Qt.BlockingConnection are the most interesting)

    See also
    --------
    QtCore.QMetaObject.invokeMethod

    Example
    -------
    >>> app = QCoreApplication.instance() or QCoreApplication([])
    >>> quit = method_invoke(app.quit, ())
    >>> t = threading.Thread(target=quit)
    >>> t.start()
    >>> app.exec()
    0
    """
    name = method.__name__
    obj = method.__self__

    if not isinstance(obj, QObject):
        raise TypeError("Require a QObject's bound method.")

    ref = weakref.ref(obj)

    # TODO: Check that the method with name exists in object's metaObject()
    def call(*args):
        obj = ref()
        if obj is None:
            return False

        args = [Q_ARG(atype, arg) for atype, arg in zip(sig, args)]
        return QMetaObject.invokeMethod(obj, name, conntype, *args)

    return call

#: Alias for `concurrent.futures.Future`
Future = concurrent.futures.Future

#: Alias for `concurrent.future.CancelledError`
CancelledError = concurrent.futures.CancelledError

#: Alias for `concurrent.future.TimeoutError`
TimeoutError = concurrent.futures.TimeoutError


class ThreadPoolExecutor(QObject, concurrent.futures.Executor):
    """
    A concurrent.futures.Executor using a QThreadPool.

    Parameters
    ----------
    parent : QObject
        Parent object.
    threadPool : QThreadPool or None
        The thread pool to use for thread allocations.
        If `None` then `QThreadPool.globalInstance()` will be used.
    trackPending : bool
        Should the `ThreadPoolExecutor` track unfinished futures in order to
        wait on them when calling `shutdown(wait=True)`. Setting this to
        `False` signifies that the executor will be shut down without waiting
        (default: True)

    See also
    --------
    concurrent.futures.Executor
    """

    def __init__(self, parent=None, threadPool=None, trackPending=True,
                 **kwargs):
        super(ThreadPoolExecutor, self).__init__(parent=parent, **kwargs)
        if threadPool is None:
            threadPool = QThreadPool.globalInstance()
        self.__threadPool = threadPool
        #: A lock guarding the internal state
        self.__lock = threading.Lock()
        #: A set of all pending uncompleted futures
        #: Since we are using possibly shared thread pool we
        #: cannot just wait on it as it can also run task from other
        #: sources, ...
        self.__pending_futures = set()
        #: Was the executor shutdown?
        self.__shutdown = False
        #: Should this executor track non-completed futures. If False then
        #: `executor.shutdown(wait=True)` will not actually wait for all
        #: futures to be done. It is the client's responsibility to keep track
        #: of the futures and their done state (use concurrent.wait)
        self.__track = trackPending

    def submit(self, fn, *args, **kwargs):
        """
        Reimplemented from `concurrent.futures.Executor.submit`
        """
        with self.__lock:
            if self.__shutdown:
                raise RuntimeError(
                    "cannot schedule new futures after shutdown")
            future = concurrent.futures.Future()

            def notify_done(future):
                with self.__lock:
                    self.__pending_futures.remove(future)

            task = TaskRunnable(future, fn, args, kwargs)
            if self.__track:
                future.add_done_callback(notify_done)
                self.__pending_futures.add(future)

            self.__threadPool.start(task)
            return future

    def shutdown(self, wait=True):
        """
        Reimplemented from `concurrent.futures.Executor.shutdown`

        Note
        ----
        If wait is True then all futures submitted through this executor will
        be waited on (this requires that they be tracked (see `trackPending`).

        This is in contrast to `concurrent.future.ThreadPoolExecutor` where
        the threads themselves are joined. This class cannot do that since it
        does not own the threads (they are owned/managed by a QThreadPool)
        """
        futures = None
        with self.__lock:
            self.__shutdown = True
            if wait:
                futures = list(self.__pending_futures)
        if wait and not self.__track:
            warnings.warn(
                "`shutdown` called with wait=True, but `trackPending` was "
                "set to False at initialization.",
                UserWarning, stacklevel=2
            )
        if wait:
            concurrent.futures.wait(futures)


class TaskRunnable(QRunnable):
    """
    A QRunnable to fulfil a `Future` in a QThreadPool managed thread.

    Parameters
    ----------
    future : concurrent.futures.Future
        Future whose contents will be set with the result of executing
        `func(*args, **kwargs)` after completion
    func : Callable
        Function to invoke in a thread
    args : tuple
        Positional arguments for `func`
    kwargs : dict
        Keyword arguments for `func`

    Example
    -------
    >>> import time
    >>> f = concurrent.futures.Future()
    >>> task = TaskRunnable(f, time.sleep, (1,), {})
    >>> QThreadPool.globalInstance().start(task)
    >>> f.result()
    """
    def __init__(self, future, func, args, kwargs):
        super(TaskRunnable, self).__init__()
        self.future = future
        self.task = (func, args, kwargs)

    def run(self):
        """
        Reimplemented from `QRunnable.run`
        """
        try:
            if not self.future.set_running_or_notify_cancel():
                # Was cancelled
                return
            func, args, kwargs = self.task
            try:
                result = func(*args, **kwargs)
            except BaseException as ex:
                self.future.set_exception(ex)
            else:
                self.future.set_result(result)
        except BaseException:
            log = logging.getLogger(__name__)
            log.critical("Exception in worker thread.", exc_info=True)


def submit(func, *args, **kwargs):
    """
    Schedule a callable `func` to run in a global QThreadPool.

    Parameters
    ----------
    func : callable
    args : tuple
        Positional arguments for `func`
    kwargs : dict
        Keyword arguments for `func`

    Returns
    -------
    future : Future
        Future with the (eventual) result of `func(*args, **kwargs)`

    Example
    -------
    >>> f = submit(pow, 10, 10)
    >>> f.result()
    10000000000
    """
    f = concurrent.futures.Future()
    task = TaskRunnable(f, func, args, kwargs)
    QThreadPool.globalInstance().start(task)
    return f


class FutureWatcher(QObject):
    """
    An `QObject` watching the state changes of a `concurrent.futures.Future`.

    Note
    ----
    The state change notification signals (`done`, `finished`, ...)
    are always emitted when the control flow reaches the event loop
    (even if the future is already completed when set).

    Note
    ----
    A `QCoreApplication` must be running, otherwise the notifier signals
    will not be emitted.

    Parameters
    ----------
    parent : QObject
        Parent object.
    future : Future
        The future instance to watch.

    Example
    -------
    >>> app = QCoreApplication.instance() or QCoreApplication([])
    >>> watcher = FutureWatcher()
    >>> watcher.done.connect(lambda f: print(f.result()))
    >>> f = submit(lambda i, j: i ** j, 10, 3)
    >>> watcher.setFuture(f)
    >>> watcher.done.connect(app.quit)
    >>> _ = app.exec()
    1000
    >>> f.result()
    1000
    """
    #: Emitted when the future is done (cancelled or finished)
    done = Signal(Future)

    #: Emitted when the future is finished (i.e. returned a result
    #: or raised an exception)
    finished = Signal(Future)

    #: Emitted when the future was cancelled
    cancelled = Signal(Future)

    #: Emitted with the future's result when successfully finished.
    resultReady = Signal(object)

    #: Emitted with the future's exception when finished with an exception.
    exceptionReady = Signal(BaseException)

    # A private event type used to notify the watcher of a Future's completion
    __FutureDone = QEvent.registerEventType()

    def __init__(self, parent=None, future=None, **kwargs):
        super(FutureWatcher, self).__init__(parent, **kwargs)
        self.__future = None  # type: concurrent.futures.Future
        if future is not None:
            self.setFuture(future)

    def setFuture(self, future):
        """
        Set the future to watch.

        Raise a `RuntimeError` if a future is already set.

        Parameters
        ----------
        future : Future
        """
        if self.__future is not None:
            raise RuntimeError("Future already set")

        self.__future = future
        selfweakref = weakref.ref(self)

        def on_done(f):
            assert f is future
            selfref = selfweakref()

            if selfref is None:
                return

            try:
                QCoreApplication.postEvent(
                    selfref, QEvent(FutureWatcher.__FutureDone))
            except RuntimeError:
                # Ignore RuntimeErrors (when C++ side of QObject is deleted)
                # (? Use QObject.destroyed and remove the done callback ?)
                pass

        future.add_done_callback(on_done)

    def future(self):
        """
        Return the future.
        """
        return self.__future

    def result(self):
        """
        Return the future's result.

        Note
        ----
        This method is non-blocking. If the future has not yet completed
        it will raise an error.
        """
        try:
            return self.__future.result(timeout=0)
        except TimeoutError:
            raise RuntimeError()

    def exception(self):
        """
        Return the future's exception.
        """
        return self.__future.exception(timeout=0)

    def __emitSignals(self):
        assert self.__future is not None
        assert self.__future.done()
        if self.__future.cancelled():
            self.cancelled.emit(self.__future)
            self.done.emit(self.__future)
        elif self.__future.done():
            self.finished.emit(self.__future)
            self.done.emit(self.__future)
            if self.__future.exception():
                self.exceptionReady.emit(self.__future.exception())
            else:
                self.resultReady.emit(self.__future.result())
        else:
            assert False

    def customEvent(self, event):
        # Reimplemented.
        if event.type() == FutureWatcher.__FutureDone:
            self.__emitSignals()
        super(FutureWatcher, self).customEvent(event)


import unittest


class TestFutures(unittest.TestCase):
    def test_futures(self):
        f = Future()
        self.assertEqual(f.done(), False)
        self.assertEqual(f.running(), False)

        self.assertTrue(f.cancel())
        self.assertTrue(f.cancelled())

        with self.assertRaises(CancelledError):
            f.result()

        with self.assertRaises(CancelledError):
            f.exception()

        f = Future()
        f.set_running_or_notify_cancel()

        with self.assertRaises(TimeoutError):
            f.result(0.1)

        with self.assertRaises(TimeoutError):
            f.exception(0.1)

        f = Future()
        f.set_running_or_notify_cancel()
        f.set_result("result")

        self.assertEqual(f.result(), "result")
        self.assertEqual(f.exception(), None)

        f = Future()
        f.set_running_or_notify_cancel()

        f.set_exception(Exception("foo"))

        with self.assertRaises(Exception):
            f.result()

        class Ref(object):
            def __init__(self, ref):
                self.ref = ref

            def set(self, ref):
                self.ref = ref

        # Test that done callbacks are called.
        called = Ref(False)
        f = Future()
        f.add_done_callback(lambda f: called.set(True))
        f.set_result(None)
        self.assertTrue(called.ref)

        # Test that callbacks are called when cancelled.
        called = Ref(False)
        f = Future()
        f.add_done_callback(lambda f: called.set(True))
        f.cancel()
        self.assertTrue(called.ref)

        # Test that callbacks are called immediately when the future is
        # already done.
        called = Ref(False)
        f = Future()
        f.set_result(None)
        f.add_done_callback(lambda f: called.set(True))
        self.assertTrue(called.ref)

        count = Ref(0)
        f = Future()
        f.add_done_callback(lambda f: count.set(count.ref + 1))
        f.add_done_callback(lambda f: count.set(count.ref + 1))
        f.set_result(None)
        self.assertEqual(count.ref, 2)

        # Test that the callbacks are called with the future as argument.
        done_future = Ref(None)
        f = Future()
        f.add_done_callback(lambda f: done_future.set(f))
        f.set_result(None)
        self.assertIs(f, done_future.ref)


class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication([])
        # if not QApplication.instance():
        #     self.app = QApplication([])
        # else:
        #     self.app = QApplication.instance()

    def test_executor(self):
        executor = ThreadPoolExecutor()
        f1 = executor.submit(pow, 100, 100)

        f2 = executor.submit(lambda: 1 / 0)

        f3 = executor.submit(QThread.currentThread)

        self.assertTrue(f1.result(), pow(100, 100))

        with self.assertRaises(ZeroDivisionError):
            f2.result()

        self.assertIsInstance(f2.exception(), ZeroDivisionError)

        self.assertIsNot(f3.result(), QThread.currentThread())

    def test_methodinvoke(self):
        executor = ThreadPoolExecutor()
        state = [None, None]

        class StateSetter(QObject):
            @Slot(object)
            def set_state(self, value):
                state[0] = value
                state[1] = QThread.currentThread()

        def func(callback):
            callback(QThread.currentThread())

        obj = StateSetter()
        f1 = executor.submit(func, method_invoke(obj.set_state, (QObject,)))
        f1.result()

        # So invoked method can be called
        QCoreApplication.processEvents()

        self.assertIs(state[1], QThread.currentThread(),
                      "set_state was called from the wrong thread")

        self.assertIsNot(state[0], QThread.currentThread(),
                         "set_state was invoked in the main thread")

        executor.shutdown(wait=True)

    def test_executor_map(self):
        executor = ThreadPoolExecutor()

        r = executor.map(pow, list(range(1000)), list(range(1000)))

        results = list(r)

        self.assertTrue(len(results) == 1000)


class TestFutureWatcher(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication([])
        # if not QApplication.instance():
        #     self.app = QApplication([])
        # else:
        #     self.app = QApplication.instance()

    def test_watcher(self):
        executor = ThreadPoolExecutor()
        watcher = FutureWatcher()
        signals = set()

        @watcher.cancelled.connect
        def on_cancelled():
            signals.add("cancelled")

        @watcher.finished.connect
        def on_finished():
            signals.add("finished")

        @watcher.done.connect
        def on_done():
            signals.add("done")

        f = executor.submit(QThread.currentThread)
        watcher.setFuture(f)
        cancelled = f.cancel()
        if not cancelled:
            f.result()

        # Flush the watcher's event queue
        QCoreApplication.sendPostedEvents(watcher, 0)

        if cancelled:
            self.assertIn("cancelled", signals)
        else:
            self.assertIn("finished", signals)
        self.assertIn("done", signals)

        executor.shutdown()

if __name__ == '__main__':
    unittest.main()