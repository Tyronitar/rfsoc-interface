import numpy as np
import valon5009
import logging
import matplotlib.pyplot as plt
import h5py
import os
import pdb

logger = logging.getLogger(__name__)


def sweep(loSource: valon5009.Synthesizer, udp, f_center, freqs, N_steps=500, freq_step=0.0):
    """
    Actually perform an LO Sweep using valon 5009's and save the data

    :param loSource:
        Valon 5009 Device Object instance
    :type loSource: valon5009.Synthesizer
    :param f_center:
        Center frequency of upconverted tones
    :param freqs: List of Baseband Frequencies returned from rfsocInterface.py's writeWaveform()
    :type freqs: List

    :param udp: udp data capture utility. This is our bread and butter for taking data from ethernet
    :type udp: udpcap.udpcap object instance

    :param N_steps: Number of steps with which to do the sweep.
    :type N_steps: Int

    Credit: Dr. Adrian Sinclair (adriankaisinclair@gmail.com)
    """
    log = logger.getChild("def-sweep")
    tone_diff = np.diff(freqs)[0] / 1e6  # MHz
    log.info(f"tone diff={tone_diff}")
    if freq_step > 0:
        flo_step = freq_step
    else:
        flo_step = tone_diff / N_steps

    log.info(f"lo step size={flo_step}")
    flo_start = f_center - flo_step * N_steps / 2.0  # 256
    flo_stop = f_center + flo_step * N_steps / 2.0  # 256

    flos = np.arange(flo_start, flo_stop, flo_step) #+1e-6
    # flos = np.round(flos * 1e3)*1e-3
    log.info(f"len flos {flos.shape}")
    udp.bindSocket()
    actual_los = []
    def temp(lofreq):
        # self.set_ValonLO function here
 
        # print(lofreq)
        loSource.set_frequency(valon5009.SYNTH_B, lofreq)
        # Read values and trash initial read, suspecting linear delay is cause..
        Naccums = 100
        I, Q = [], []
        for i in range(20):  # toss 10 packets in the garbage
            udp.parse_packet()

        for i in range(Naccums):
            # d = udp.parse_packet()
            d = udp.parse_packet()
            It = d[::2]
            Qt = d[1::2]
            I.append(It)
            Q.append(Qt)
        I = np.array(I)
        Q = np.array(Q)
        Imed = np.median(I, axis=0)
        Qmed = np.median(Q, axis=0)

        Z = Imed + 1j * Qmed
        start_ind = np.min(np.argwhere(Imed != 0.0))
        Z = Z[start_ind : start_ind + len(freqs)]

        print(".", end="")

        return Z
    sweep_Z = np.array([temp(lofreq) for lofreq in flos])
    log.info(f"sweepz.shape={sweep_Z.shape}")

    f = np.zeros([np.size(freqs), np.size(flos)])
    log.info(f"shape of f = {f.shape}")
    for itone, ftone in enumerate(freqs):
        f[itone, :] = flos * 1.0e6 + ftone
    #    f = np.array([flos * 1e6 + ftone for ftone in freqs]).flatten()
    sweep_Z_f = sweep_Z.T
    #    sweep_Z_f = sweep_Z.T.flatten()
    udp.release()
    ## SAVE f and sweep_Z_f TO LOCAL FILES
    # SHOULD BE ABLE TO SAVE TARG OR VNA
    # WITH TIMESTAMP

    # set the LO back to the original frequency
    loSource.set_frequency(valon5009.SYNTH_B, f_center)

    return (f, sweep_Z_f)


def loSweep(
    loSource,
    udp,
    freqs=[],
    f_center=400.0,
    N_steps=500,
    freq_step=1.0,
    savefile="s21",
):
    """Perform a stepped frequency sweep centered at f_center and save result as s21.npy file

    f_center: center frequency for sweep in [MHz], default is 400
    """
    #    print(freqs)
    f, sweep_Z_f = sweep(
        loSource,
        udp,
        f_center,
        np.array(freqs),
        N_steps=N_steps,
        freq_step=freq_step,
    )
    np.save(savefile + ".npy", np.array((f, sweep_Z_f)))
    print("LO Sweep s21 file saved.")


def plot_sweep(s21: str):
    log = logger.getChild("def plot_sweep")

    data = np.load(s21)
    log.info(f"s21 shape={data.shape}")
    ftones = np.concatenate(data[0])
    sweep_Z = np.concatenate(data[1])
    # ftones = data[0][0]
    # sweep_Z = data[1][0]
    mag = 10 * np.log10(np.abs(sweep_Z))

    plt.figure(figsize=(14, 8))
    plt.plot(ftones, mag.real)
    plt.grid()
    plt.show()


def plot_sweep_hdf(path: str):
    """
    plots sweep from provided path to RawDataFile if it exists.

    :param str path:
        path to RawDataFile
    """
    log = logger.getChild("def plot_sweep_hdf")

    if os.path.isfile(path):
        f = h5py.File(path, 'r')
    else:
        log.error("specified hdf5 file not found")
    if "/global_data/lo_sweep" in f:
        data = f["/global_data/lo_sweep"]
    else:
        log.error("No Sweep Data Found")
    data = data[:]
    log.info(f"s21 shape={data.shape}")
    ftones = np.concatenate(data[0])
    sweep_Z = np.concatenate(data[1])
    # ftones = data[0][0]
    # sweep_Z = data[1][0]
    mag = 10 * np.log10(np.abs(sweep_Z))

    plt.figure(figsize=(14, 8))
    plt.plot(ftones, mag.real)
    plt.grid()
    plt.show()