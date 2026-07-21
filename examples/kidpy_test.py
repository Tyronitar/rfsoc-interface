import time 

from kidpy3 import capture, RawDataFile
import numpy as np
import pdb

from rfsocinterface.core.rfsoc import RFSOCWrapper
from rfsocinterface.core.settings import Settings
from rfsocinterface.core.utils import get_filename, PERMISSIONS_USR_RW

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import h5py
from scipy.stats import norm
from tqdm import tqdm


matplotlib.rcParams.update({
    "font.family":        "serif",
    "font.serif":         ["Times New Roman", "DejaVu Serif"],
    "font.size":          11,
    "axes.titlesize":     16,
    "axes.labelsize":     16,
    "xtick.labelsize":    14,
    "ytick.labelsize":    14,
    "legend.fontsize":    18,
    "figure.dpi":         150,
    "savefig.dpi":        300,
    "savefig.bbox":       "tight",
    "axes.linewidth":     0.8,
    "grid.linewidth":     0.5,
    "lines.linewidth":    1.2,
    "text.usetex":        False,
})



def collect_data(duration: int):
    start = time.time()
    elapsed_time = 0
    with tqdm(
        total=duration,
        unit='s',
        desc='Collecting data',
        bar_format='{l_bar}{bar}| [{elapsed}<{remaining}, {rate_fmt}{postfix}]',
    ) as pbar:
        while elapsed_time < duration:
            elapsed_time = time.time() - start
            current_progress = min(elapsed_time, duration)
            pbar.n = current_progress
            pbar.refresh()
            time.sleep(1.e-2)
    print('Done collecting data')

def calc_packet_perf(file: str):
    with (h5py.File(file, 'r') as fd):
        print("Reading data")

        print(f'ADC_I shape: {fd["time_ordered_data/adc_i"].shape}')
        print(f'ADC_I chunks: {fd["time_ordered_data/adc_i"].chunks}')

        nsamp = fd["dimension/n_sample"][0]
        indx: np.ndarray = fd["time_ordered_data/pkt_idx"][0:nsamp].astype(np.int64)
        ts: np.ndarray = fd["time_ordered_data/timestamp"][0:nsamp].astype(np.float64)
        dtype_size_bytes = np.dtype(fd['time_ordered_data/adc_i'].dtype).itemsize
        data_set_size_bytes = dtype_size_bytes * fd['time_ordered_data/adc_i'].size
        data_size_mb = data_set_size_bytes * 1e-6
        load_time_start = time.perf_counter_ns()
        _ = fd["time_ordered_data/adc_i"][...]
        load_time_end = time.perf_counter_ns()
        time_s = (load_time_end - load_time_start) / 1e9
        print(f'Time to read: {time_s:.3f} seconds')
        print(f'Read Throughput: {data_size_mb / time_s:.3f} MB/s')
        ts_delta = np.diff(ts)[1:]*1000
        indx_delta = np.diff(indx)
        mu = np.mean(ts_delta)
        sigma = np.std(ts_delta)
        onesigma = np.count_nonzero([(ts_delta > mu - sigma) & (ts_delta < mu + sigma)])
        twosigma = np.count_nonzero([(ts_delta > mu - 2*sigma) & (ts_delta < mu + 2*sigma)])
        threesigma = np.count_nonzero([(ts_delta > mu - 3 * sigma) & (ts_delta < mu + 3 * sigma)])
        print(f"AVG $\\Delta$ Timestamp (milliseconds): {np.average(ts_delta):.8f}")
        print(f"MED $\\Delta$ Timestamp (milliseconds): {np.median(ts_delta):.8f}")
        print(f"MAX $\\Delta$ Timestamp (milliseconds): {np.max(ts_delta):.8f}")
        print(f"MIN $\\Delta$ Timestamp (milliseconds): {np.min(ts_delta):.8f}")
        print(f"STD DEV $\\Delta$ Timestamp (milliseconds): {sigma:.8f}")
        print("AVG $\\Delta$ Index: ", np.average(indx_delta[1:]))
        print("MED $\\Delta$ Index: ", np.median(indx_delta[1:]))
        print("MAX $\\Delta$ Index:", np.max(indx_delta[1:]))
        dp = np.count_nonzero(indx_delta >=2)
        l = indx_delta.shape[0]
        print(f"Number of dropped packets/samples: {dp} out of {l}, {dp/l*100:.2f}%")
        print(f"Number of timestamps within 1σ: {onesigma} \n\t {onesigma/l*100:.2f}% of $\\Delta$ timestamps")
        print(f"Number of timestamps within 2σ: {twosigma} \n\t {twosigma/l*100:.2f}% of $\\Delta$ timestamps")
        print(f"Number of timestamps within 3σ: {threesigma} \n\t {threesigma / l * 100:.2f}% of $\\Delta$ timestamps")
        # plt.close("all")
        #
        # fig = plt.figure(figsize=(10, 6))
        # ax = plt.axes((0.1, 0.1, 0.5, 0.8))
        # ax.minorticks_on()
        # plt.plot(ts_delta[1:])
        # plt.xlabel("Sample")
        # plt.ylabel("Δ Timestamp (Seconds)")
        # fig.savefig("ts_delta.pdf", dpi=300)
        # #
        # fig = plt.figure(figsize=(10, 6))
        # ax = plt.axes((0.1, 0.1, 0.5, 0.8))
        # ax.minorticks_on()
        plt.stem(indx_delta[1:])
        plt.xlabel("Sample")
        plt.ylabel("Δ Packet Counter")
        plt.minorticks_on()
        plt.savefig('fig.png')
        pdb.set_trace()
        # fig.savefig("index_delta.pdf", dpi=300)
        # plt.savefig("indx_delta.png")
        #
        #
        # plt.figure(figsize=(12, 6))
        # plt.plot(indx_delta[1:], ts_delta[1:], 'x')
        # plt.xlabel("Sample")
        # plt.ylabel("Index vs ts")
        # plt.savefig("indxvsts.png")
        # plt.show()
        # histdat_1 = np.extract(indx_delta[1:] == 1, ts_delta[1:])
        # histdat_2 = np.extract(indx_delta[1:] == 2, ts_delta[1:])
        # print("Delta 1 average", np.average(histdat_1))
        # print("Delta 2 average", np.average(histdat_2))
        #
        # mu, sigma = norm.fit(histdat_1)
        # mu2, sigma2 = norm.fit(histdat_2)
        # BINS = 100
        # xs1 = np.linspace(histdat_1.min(), histdat_1.max(), 500)
        # xs2 = np.linspace(histdat_2.min(), histdat_2.max(), 500)
        # pdf = norm.pdf(xs1, mu, sigma)
        # pdf2 = norm.pdf(xs2, mu2, sigma2)
        #
        # counts, edges = np.histogram(histdat_1, bins=BINS)
        # bin_width1 = edges[1] - edges[0]
        # counts2, edges2 = np.histogram(histdat_2, bins=BINS)
        # bin_width2 = edges2[1] - edges2[0]
        #
        # scale = len(histdat_1) * bin_width1
        # scale2 = len(histdat_2) * bin_width2
        # curve = scale * pdf
        # curve2 = scale2 * pdf2
        #
        # plt.figure(figsize=(12, 6))
        #
        # plt.plot(xs1, curve, label="Delta=1")
        # plt.hist(histdat_1, bins=BINS, linewidth=0.5, range=(0,0.006), edgecolor="white")
        #
        # plt.grid()
        # plt.xlabel("Timestamp Deltas", fontsize=18)
        # plt.ylabel("Count", fontsize=18)
        # plt.legend()
        #
        # plt.savefig("hist_1.png")
        #
        #
        #
        # plt.figure(figsize=(12, 6))
        #
        # plt.plot(xs2, curve2, label="Delta=2")
        # plt.hist(histdat_2, bins=BINS, linewidth=0.5, range=(0,0.006), edgecolor="white")
        #
        # plt.grid()
        # plt.xlabel("Timestamp Deltas", fontsize=18)
        # plt.legend()
        # plt.ylabel("Count", fontsize=18)
        # plt.savefig("hist_2.png")
        # plt.show()


if __name__ == '__main__':
    # Prepare RFSoC
    # settings = Settings()
    # settings.load_settings()
    # rfsoc_settings = settings['rfsocs'][0]  # Just take the first one for testing
    # rfsoc = RFSOCWrapper(rfsoc_settings)
    # rfchan = rfsoc.get_channel(1)
    # save_location = get_filename(file_type='tod', tile_name=rfchan.tile_name, mkdir=True).with_suffix('.h5')
    # rfchan.raw_filename = str(save_location)

    # Collect data
    # duration = 30 * 60
    # print(f'Collecting {duration} seconds of data to "{save_location}"')
    # capture([rfchan], collect_data, duration)

    # Analyze performance
    # save_location = '/data/20260720/20260720_Be231102p2_TOD_set1010.h5'
    save_location = '/data/20260520/20260520_100_tone_uniform_202050829_TOD_set1003.h5'
    calc_packet_perf(save_location)
