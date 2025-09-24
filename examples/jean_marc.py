import time

from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.settings import Settings

from rfsocinterface.core.utils import get_filename, PERMISSIONS_USR_RW

from kidpy3 import capture


if __name__ == "__main__":
    # Load the settings and initialize the RFSOC
    settings = Settings()
    settings.load_settings()
    rfsoc = RFSOCWrapper(settings['rfsocs'][0])  # Just use the first RFSOC for this example


    # Load parameters file of your choice (contains LO frequency, tone frequencies, etc.)
    parameters_file = '[INSERT PARAMS FILE PATH HERE]'
    # The tones should not be uploaded after performing the LO sweep, as the phases will be randomized
    rfsoc.load_params_file(
        parameters_file,
        upload_tones=False,  
    )

    # Set the location to save the TOD file (will go to /data/YYYYMMDD/YYYYMMDD_<tile_name>_TOD_set<setnum>.h5 by default)
    rfchan = rfsoc.get_channel(1)
    save_location = get_filename(file_type='tod', chan_name=rfchan.tile_name)
    save_location.touch(PERMISSIONS_USR_RW, exist_ok=True)
    rfchan.raw_filename = str(save_location)

    # Collect data for 10 seconds
    duration = 10  # seconds
    capture([rfchan], time.sleep, duration)



