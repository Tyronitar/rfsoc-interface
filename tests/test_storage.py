from pathlib import Path

import h5py

from rfsocinterface.core.data.storage import NewDataStorage
from rfsocinterface.core.utils import DEFAULT_DATA_DIRECTORY


class DummyStorage(NewDataStorage):
    @staticmethod
    def get_template(date, setnum, data_dir=DEFAULT_DATA_DIRECTORY):
        return f"{date}-{setnum}-{data_dir}"


def test_load_accepts_positional_mode_for_filename(tmp_path):
    path = tmp_path / "example.h5"
    with h5py.File(path, "w"):
        pass

    storage = DummyStorage.load(str(path), "r")
    assert storage.filename == Path(path)
    assert storage.mode == "r"
    storage.close()


def test_load_accepts_positional_mode_for_date_and_setnum(tmp_path):
    path = tmp_path / "example.h5"
    with h5py.File(path, "w"):
        pass

    class TemplateStorage(NewDataStorage):
        @staticmethod
        def get_template(date, setnum, data_dir=DEFAULT_DATA_DIRECTORY):
            return str(path)

    storage = TemplateStorage.load("20240101", 3, "r")
    assert storage.filename == Path(path)
    assert storage.mode == "r"
    storage.close()
