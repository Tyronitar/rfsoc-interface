"""Functions for analyzing beam maps."""

import pdb

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.offsetbox import AnchoredText
from mpl_toolkits.axes_grid1 import make_axes_locatable
import numpy as np
import numpy.typing as npt
import tables
from scipy.optimize import curve_fit

from rfsocinterface.core.data import MapData


def Gauss_2d(
    xy_coords: tuple[npt.NDArray, npt.NDArray],
    amp: float,
    x0: float,
    y0: float,
    fwhm_x: float,
    fwhm_y: float,
    offset: float,
) -> npt.NDArray:
#  return offset + amp * np.exp(-((x-x0)**2 + (y-y0)**2)/ (2. * sigma**2))
  (x,y) = xy_coords
  sigma_x = fwhm_x / (2 * np.sqrt(2 * np.log(2)))
  sigma_y = fwhm_y / (2 * np.sqrt(2 * np.log(2)))
  return offset + amp * np.exp(-(x-x0)**2/(2.*sigma_x**2) - (y-y0)**2/(2.*sigma_y**2))


def analyze_beammap(
    map_data: MapData,
    nrows: int=10,
    ncols: int=10,
    show_all: bool=False,
):
    az = map_data.map_az[:][:, np.newaxis]
    za = map_data.map_za[:][np.newaxis, :]
    map_val = map_data.map  # N_resonator x X x Y

    extent = map_data.extent()

    filename = map_data.beammap_file_template

    # if show_all:
    #     chanmask = np.ones(map_data.n_tones)
    # else:
    chanmask = map_data.chanmask[:]
    # chanmask = chanmask[:100]

    beammap_file = tables.File(filename, 'w')
    az_center = beammap_file.create_array('/', 'az_center', shape=np.shape(chanmask), atom=tables.Float64Atom())
    za_center =beammap_file.create_array('/', 'za_center', shape=np.shape(chanmask), atom=tables.Float64Atom())
    amplitude  = beammap_file.create_array('/', 'amplitude', shape=np.shape(chanmask), atom=tables.Float64Atom())
    snr = beammap_file.create_array('/', 'snr', shape=np.shape(chanmask), atom=tables.Float64Atom())
    chisq = beammap_file.create_array('/', 'chisq', shape=np.shape(chanmask), atom=tables.Float64Atom())
    fwhm_az = beammap_file.create_array('/', 'fwhm_az', shape=np.shape(chanmask), atom=tables.Float64Atom())
    fwhm_za = beammap_file.create_array('/', 'fwhm_za', shape=np.shape(chanmask), atom=tables.Float64Atom())

    for idx in np.flatnonzero(chanmask == 1):
        this_val = np.ndarray.flatten(map_val[idx,:])
        this_val[np.isnan(this_val)] = 0

        max_index = np.argwhere(this_val == np.max(this_val))
        az_idx, za_idx = np.unravel_index(max_index[0], map_val[idx].shape)
        az_max = az[az_idx, :]
        za_max = za[:, za_idx]
        separation = np.sqrt((az - az_max[0])**2 + (za - za_max[0])**2)
        index = np.argwhere(separation < 0.1)
        flat_index = np.ravel_multi_index((index[:, 0], index[:, 1]), map_val[idx].shape)

        az_center[idx] = np.sum(az[index[:, 0]].squeeze()*this_val[flat_index]) / np.sum(this_val[flat_index])
        za_center[idx] = np.sum(za[:, index[:, 1]].squeeze()*this_val[flat_index]) / np.sum(this_val[flat_index])
        amplitude[idx] = np.max(this_val[index])

        this_az = np.ndarray.flatten(az[index[:, 0], :])
        this_za = np.ndarray.flatten(za[:, index[:, 1]])
        this_val = this_val[flat_index]
        sigma_z = np.full(int(np.size(this_val)), (np.percentile(this_val, 84) - np.percentile(this_val, 16)) * 0.5)
        start_params = (
            np.max(this_val),
            az_center[idx],
            za_center[idx],
            0.1,
            0.1,
            np.median(this_val)
        )  
        bounds = (
            (0., az_center[idx] - 0.2, za_center[idx] - 0.2, 0.01, 0.01, -np.max(np.abs(this_val))),
            (10. * np.max(this_val), az_center[idx] + 0.2, za_center[idx] + 0.2, 1., 1., np.max(np.abs(this_val)))
        )
        try:
            popt, pcov = curve_fit(
                Gauss_2d,
                (this_az, this_za),
                this_val,
                p0=start_params,
                sigma=sigma_z,
                absolute_sigma=True,
                maxfev=10000,
                bounds=bounds
            )
        except RuntimeError:
            popt = np.zeros(6)
            pcov = np.zeros((6, 6))
            continue
        az_center[idx] = popt[1]
        za_center[idx] = popt[2]
        amplitude[idx] = popt[0]
        fwhm_az[idx] = np.abs(popt[3])
        fwhm_za[idx] = np.abs(popt[4])
        snr[idx] = popt[0] / np.sqrt(pcov[0, 0])
        #if idx == 14:
        #pdb.set_trace()  # Debugging breakpoint for channel 14
        chisq[idx] = np.sum(
            ((this_val - Gauss_2d(
                (this_az, this_za),
                popt[0], popt[1], popt[2], popt[3], popt[4], popt[5]
                )) ** 2 / sigma_z ** 2) / (np.size(this_val) - 5.)
        )


    # TODO: file name
    pdf_file_name = str(map_data.folder / map_data.file_stub) + '_beammap.pdf'

    with PdfPages(pdf_file_name) as pdf:
        FOM = np.divide(amplitude, chisq, out=np.zeros_like(amplitude), where=chisq!=0)
        high_snr_ind = np.argwhere(np.bitwise_and(amplitude > np.percentile(amplitude,55), FOM > 50)).flatten()
        plt.scatter(az_center[high_snr_ind], za_center[high_snr_ind], marker='+')
        plt.axis('equal')
        plt.xlim(extent[0],extent[1])
        plt.ylim(extent[2],extent[3])
        plt.xlabel('X Position (deg)')
        plt.ylabel('Y Position (deg)')
        pdf.savefig()
        plt.close()
        
        counter = 1
        for idx in range(map_data.n_tones):
        # for idx in np.argwhere(chanmask == 1).flatten():
            if not show_all and chanmask[idx] != 1:
                continue

            if counter == 1:
                fig, axes = plt.subplots(nrows, ncols)
                fig.set_dpi(300)  # Sharper plots
                for ax in axes.flatten():
                    ax.set_axis_off()
            ax = axes.flatten()[counter - 1]
            ax.imshow(np.flip(np.transpose(map_val[idx, ::-1]), 1), extent=extent, aspect='equal', cmap='jet', interpolation='bilinear')


            
            # Draw a rectangle around the subplot indicating off resonance
            if show_all and chanmask[idx] == 0:
            # if show_all and idx == 1:
                auto_axis = ax.axis()
                # bbox = ax.get_window_extent().bounds
                rec = plt.Rectangle(
                    # bbox[:2],
                    # bbox[2],
                    # bbox[3],
                    (auto_axis[0], auto_axis[2]),
                    auto_axis[1] - auto_axis[0],
                    auto_axis[3] - auto_axis[2],
                    fill=False,
                    lw=2,
                    edgecolor='orange',
                )
                rec = ax.add_patch(rec)
                # fig.patches.append(rec)
                rec.set_clip_on(False)
                # ax.set_facecolor('orange')

            if counter == nrows*ncols:
                pdf.savefig(fig)
                plt.close()
                counter = 0
            counter +=1
        
        if counter > 1:
            pdf.savefig(fig)
        # plt.show()
        plt.close()

        for idx in range(map_data.n_tones):
        # for idx in np.argwhere(chanmask == 1).flatten():
            if not show_all and chanmask[idx] != 1:
                continue
            fig, ax = plt.subplots()
            data_to_plot = np.flip(np.transpose(map_val[idx, ::-1]), 1)
            data_to_plot -= np.nanmedian(data_to_plot)
            data_to_plot /= np.nanmax(data_to_plot)
            # data_to_plot = 10 * np.log10(np.abs(data_to_plot))
            im = ax.imshow(
                data_to_plot,
                # vmin=-10,
                # vmax=0,
                extent=extent,
                aspect='equal',
                cmap='jet',
                # interpolation='bilinear',
            )
            divider = make_axes_locatable(ax)
            cax = divider.append_axes('right', size='5%', pad=0.05)
            fig.colorbar(im, cax=cax)
            ax.set_xlabel('X Position (deg)')
            ax.set_ylabel('Y Position (deg)')
            ax.set_xlim(extent[1],extent[0])
            ax.set_ylim(extent[2],extent[3])
            title = f'Resonator {idx}'
            
            # Indicate in plot title if off-resonance
            if show_all and chanmask[idx] == 0:
            # if show_all and idx == 1:
                title += ' (Off-resonance)'
            ax.set_title(title)
            ax.plot(az_center[idx],za_center[idx],marker='+',color='white', markersize=10, mew=2)

            bbox_pad = 0.3
            t = AnchoredText(
                f'Amplitude = {amplitude[idx]}\n'
                f'SNR = {snr[idx]}\n'
                f'chisq = {chisq[idx]}\n'
                f'fwhm_az = {fwhm_az[idx]}\n'
                f'fwhm_za = {fwhm_za[idx]}',
                loc='upper left',
                pad=bbox_pad,
                borderpad=0,
                prop=dict(
                    color='white',
                ),
            )
            t.patch.set_alpha(0.25)
            t.patch.set_color('black')
            ax.add_artist(t)
            fig.set_dpi(300)
            # fig.tight_layout()

            # Set face color to orange to indicate off-resonance
            if show_all and map_data.chanmask[idx] == 0:
            # if show_all and idx == 1:
                fig.set_facecolor('orange')

            pdf.savefig(fig)
            # if idx == 1:
            #     plt.show()
                # fig.show()
            plt.close()
    beammap_file.close()


if __name__ == '__main__':
    # date = '20250729'
    # setnum = 1012
    date = '20251212'

    setnum = 1003

    # md = MapData.from_file(date, setnum, 'r')
    md = MapData.from_file(date, setnum)
    # for i in range(240, 250):
    #     md.plot_individual(i)
    #     plt.show(block=False)
    # pdb.set_trace()
    analyze_beammap(md, show_all=True)
    md.close()