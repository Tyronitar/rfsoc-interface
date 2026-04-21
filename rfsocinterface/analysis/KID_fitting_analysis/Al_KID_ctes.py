
import numpy as np 

R = 7.2 # [um^3/s] Quasiparticle recombination rate (S. Siegel thesis, p112)
N0 = 1.71e10 # [eV/um^3] Single spin electron density of states at the Fermi level (S. Siegel thesis, p44)
tau_0 = 430e-9 # [s] Intrinsic quasiparticle lifetime for Al (S. Siegel thesis, p112)
Tc = 1.2 # [K] Critical temperature of Al (could lso be 1.1K)
n_ph = np.array([0.57, 0.57, 0.57, 0.57])
labs = np.array([1.5, 1.5, 1.5, 1.5])*22*1e3 # [um] Al inductor length (each branch is 1.5 mm long and there are 22 meanders)
wabs = 1 # [um] Al inductor width
tabs = 100e-3 # [um] Al inductor thickness
V_Al = labs*wabs*tabs # [um^3] Volume of Al inductor, by band, as designed by S.Shu
dv = np.array([47, 45, 40, 34])*1e9 # [Hz] mm-wave frequency bands
v_mid = np.array([150, 230, 275, 350])*1e9 # [Hz] mm-wave frequency bands bandwidth
n_abs = 0.8 # mm-wave absorption efficiency in TiN inductor
# A_C = np.array([0.83, 0.51, 0.53, 0.26, 0.27, 0.34]) # [mm^2] Capacitor area
# alpha = 0.99 # kinetic inductance fraction


