import numpy as np
import matplotlib.pyplot as plt
import h5py
from scipy.stats import norm
import pdb


def main():
    with (h5py.File("/data/20250908/20250908_30_tone_uniform_202050829_TOD_set1008.h5", 'r') as fd):
        print("Reading data")

        adc_i: np.ndarray = fd["time_ordered_data/adc_i"][...]
        adc_q: np.ndarray = fd["time_ordered_data/adc_q"][...]
        indx: np.ndarray = fd["time_ordered_data/pkt_idx"][...]
        ts: np.ndarray = fd["time_ordered_data/timestamp"][...]
        ts_delta = np.diff(ts)
        indx_delta = np.diff(indx)
        print(f"AVG Δ Timestamp (seconds): {np.average(ts_delta[1:]):.8f}")
        print(f"MED Δ Timestamp (seconds): {np.median(ts_delta[1:]):.8f}")
        print(f"MAX Δ Timestamp (seconds): {np.max(ts_delta[1:]):.8f}")
        print(f"MIN Δ Timestamp (seconds): {np.min(ts_delta[1:]):.8f}")
        print("AVE Δ Index: ", np.average(indx_delta[1:]))
        print("MED Δ Index: ", np.median(indx_delta[1:]))
        print("MAX Δ Index:", np.max(indx_delta[1:]))
        dp = np.count_nonzero(indx_delta >=2)
        l = indx_delta.shape[0]
        print(f"Number of dropped packets/samples: {dp} out of {l}, {dp/l*100:.2f}%")

        plt.close("all")
        plt.figure(figsize=(12, 6))
        plt.plot(ts_delta[1:])
        plt.xlabel("Sample")
        plt.ylabel("Δ Timestamp (Seconds)")
        plt.savefig("ts_delta.png")
        
        plt.figure(figsize=(12, 6))
        plt.stem(indx_delta[1:])
        plt.xlabel("Sample")
        plt.ylabel("Δ Packet Counter")
        plt.savefig("indx_delta.png")
        
        
        plt.figure(figsize=(12, 6))
        plt.plot(indx_delta[1:], ts_delta[1:], 'x')
        plt.xlabel("Sample")
        plt.ylabel("Index vs ts")
        plt.savefig("indxvsts.png")
        plt.show()
        histdat_1 = np.extract(indx_delta[1:] == 1, ts_delta[1:])
        histdat_2 = np.extract(indx_delta[1:] == 2, ts_delta[1:])
        pdb.set_trace()
        print("Delta 1 average", np.average(histdat_1))
        print("Delta 2 average", np.average(histdat_2))

        mu, sigma = norm.fit(histdat_1)
        mu2, sigma2 = norm.fit(histdat_2)
        BINS = 100
        xs1 = np.linspace(histdat_1.min(), histdat_1.max(), 500)
        xs2 = np.linspace(histdat_2.min(), histdat_2.max(), 500)
        pdf = norm.pdf(xs1, mu, sigma)
        pdf2 = norm.pdf(xs2, mu2, sigma2)

        counts, edges = np.histogram(histdat_1, bins=BINS)
        bin_width1 = edges[1] - edges[0]
        counts2, edges2 = np.histogram(histdat_2, bins=BINS)
        bin_width2 = edges2[1] - edges2[0]

        scale = len(histdat_1) * bin_width1
        scale2 = len(histdat_2) * bin_width2
        curve = scale * pdf
        curve2 = scale2 * pdf2

        plt.figure(figsize=(12, 6))

        plt.plot(xs1, curve, label="Delta=1")
        plt.hist(histdat_1, bins=BINS, linewidth=0.5, range=(0,0.006), edgecolor="white")

        plt.grid()
        plt.xlabel("Timestamp Deltas", fontsize=18)
        plt.ylabel("Count", fontsize=18)
        plt.legend()

        plt.savefig("hist_1.png")



        plt.figure(figsize=(12, 6))

        plt.plot(xs2, curve2, label="Delta=2")
        plt.hist(histdat_2, bins=BINS, linewidth=0.5, range=(0,0.006), edgecolor="white")

        plt.grid()
        plt.xlabel("Timestamp Deltas", fontsize=18)
        plt.legend()
        plt.ylabel("Count", fontsize=18)
        plt.savefig("hist_2.png")
        plt.show()




if __name__ == "__main__":
    main()
