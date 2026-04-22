## NEW-MUSIC: HotCold script
## Novermber 2024, Fabian deFrance fdefranc@caltech.edu, Adriana Gavidia(agavidia@caltech.edu)

# Mattis-Bardeen functions
import numpy as np


def integrand_Delta_gap(E, Delta, Tk, G, Delta0):
    f1 = np.tanh(E/Tk/2)
    DOS1 = np.real(1 / np.sqrt(E*E - (Delta0 - G*1j)**2))
    DOS2 = np.real(1 / np.sqrt(E*E - (Delta - G*1j)**2))
    return DOS1 - f1 * DOS2


def integrand_Delta_nogap(E, Delta, Tk, Delta0):
    f1 = 2/(np.exp(E/Tk)+1)
    DOS1 = 1 / np.sqrt(E + Delta)
    return f1 * DOS1


def integrand_nqp_gap(E, Delta, Tk, G):
    f1 = E / (np.exp(E/Tk) + 1)
    DOS1 = np.real(1 / np.sqrt(E*E - (Delta - G*1j)**2))
    return f1 * DOS1


def integrand_nqp_nogap(E, Delta, Tk):
    f1 = E / (np.exp(E/Tk) + 1)
    DOS1 = 1 / np.sqrt(E + Delta)
    return f1 * DOS1


def integrand_s1_gap(E, Delta, Tk, G, whbar):
    f1 = 1 / (np.exp(E/Tk) + 1)
    f2 = 1 / (np.exp((E + whbar)/Tk) + 1)
    M = E*E + Delta*Delta + whbar*E
    # Note that this formulation differs from Dynes et al
    # Gap parameter is given an imaginary part instead of energy
    DOS1 = np.real(1 / np.sqrt(E*E - (Delta - G*1j)**2))
    DOS2 = np.real(1 / np.sqrt((E+whbar)*(E+whbar) - (Delta - G*1j)**2))
    return (f1 - f2) * M * DOS1 * DOS2


def integrand_s1_nogap(E, Delta, Tk, whbar):
    f1 = 1 / (np.exp(E/Tk) + 1)
    f2 = 1 / (np.exp((E + whbar)/Tk) + 1)
    M = E*E + Delta*Delta + whbar*E
    DOS1 = 1 / np.sqrt(E + Delta)
    DOS2 = 1 / np.sqrt((E+whbar)*(E+whbar) - Delta*Delta)
    return (f1 - f2) * M * DOS1 * DOS2


def integrand_s2_gap(E, Delta, Tk, G, whbar):
    f1 = 1 / (np.exp(E/Tk) + 1)
    M = E*E + Delta*Delta - whbar*E
    # Note that this formulation differs from Dynes et al
    # Gap parameter is given an imaginary part instead of energy
    DOS1 = np.real(1 / np.sqrt(E*E - (Delta - G*1j)**2))
    DOS2 = np.real(1 / np.sqrt(-(E-whbar)*(E-whbar) + (Delta - G*1j)**2))
    return (1 - 2*f1) * M * DOS1 * DOS2


def integrand_s0_gap(E, Delta, G, whbar):
    M = E*E + Delta*Delta - whbar*E
    # Note that this formulation differs from Dynes et al
    # Gap parameter is given an imaginary part instead of energy
    DOS1 = np.real(1 / np.sqrt(E*E - (Delta - G*1j)**2))
    DOS2 = np.real(1 / np.sqrt(-(E-whbar)*(E-whbar) + (Delta - G*1j)**2))
    return M * DOS1 * DOS2


def integrand_s0_minus_s2_gap(E, Delta, Tk, G, whbar):
    f1 = 1 / (np.exp(E/Tk) + 1)
    M = E*E + Delta*Delta - whbar*E
    # Note that this formulation differs from Dynes et al
    # Gap parameter is given an imaginary part instead of energy
    DOS1 = np.real(1 / np.sqrt(E*E - (Delta - G*1j)**2))
    DOS2 = np.real(1 / np.sqrt(-(E-whbar)*(E-whbar) + (Delta - G*1j)**2))
    return 2*f1 * M * DOS1 * DOS2


def integrand_s2_nogap(E, Delta, Tk, whbar):
    f1 = 1 / (np.exp(E/Tk) + 1)
    M = E*E + Delta*Delta - whbar*E
    DOS1 = 1 / np.sqrt(E + Delta)
    DOS2 = 1 / np.sqrt(Delta + E - whbar)
    return (1 - 2*f1) * M * DOS1 * DOS2


def integrand_s0_nogap(E, Delta, whbar):
    M = E*E + Delta*Delta - whbar*E
    DOS1 = 1 / np.sqrt(E + Delta)
    DOS2 = 1 / np.sqrt(Delta + E - whbar)
    return M * DOS1 * DOS2


def integrand_s0_minus_s2_nogap(E, Delta, Tk, whbar):
    f1 = 1 / (np.exp(E/Tk) + 1)
    M = E*E + Delta*Delta - whbar*E
    DOS1 = 1 / np.sqrt(E + Delta)
    DOS2 = 1 / np.sqrt(Delta + E - whbar)
    return 2*f1 * M * DOS1 * DOS2

