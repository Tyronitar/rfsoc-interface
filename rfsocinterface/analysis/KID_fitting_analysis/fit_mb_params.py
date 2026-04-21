import lmfit as lf
import scipy.special as sp
import numpy as np
from scipy import LowLevelCallable 
import scipy.integrate as integrate
import pdb
import warnings, os, ctypes
from rfsocinterface.analysis.KID_fitting_analysis.phys_ctes import kb_J, kb_eV, h_J, h_eV, hbar_eV, hbar_J, pi, eV2J
from rfsocinterface.analysis.KID_fitting_analysis.Al_KID_ctes import N0, v_mid, dv, n_abs, R, V_Al, tau_0, n_ph     
xi = lambda omega, T: (hbar_eV  * omega)/(2* kb_eV * T)

import numpy as np





# Approximate value of nqp without gap
def get_nqp(T, delta_0, N0=N0, mu=0): 
    # delta = get_delta(delta_0, T)
    return 4 * N0 * delta_0 * np.exp((mu)/(kb_eV * T)) * sp.kn(1, delta_0/(kb_eV*T))

# k1 calculation
def get_k1(omega, T, delta_0, N0=N0):
    # delta = get_delta(delta_0, T)
    k1 = 1/(np.pi*N0*delta_0) * np.sqrt(2*delta_0/(np.pi*kb_eV*T)) * np.sinh(xi(omega, T)) * sp.kn(0, xi(omega, T))
    return k1

# k2 calculation
def get_k2(omega, T, delta_0, N0=N0):
    # delta = get_delta(delta_0, T)
    k2 = 1/(2*N0*delta_0) * (1 + np.sqrt(2*delta_0/(np.pi*kb_eV*T)) * np.exp(-xi(omega, T)) * sp.iv(0, xi(omega, T)))
    return k2
       

def minimize_f_for_lmfit(params, Tlist, freslist):
    Emin = 0
    N = np.size(Tlist)  
    arrArgs = ctypes.c_double * 5
    # fnqp = ctypes.CDLL(os.path.abspath('func_nqp_real.so'))
    fnqp = ctypes.CDLL(os.path.abspath('rfsocinterface/analysis/KID_fitting_analysis/func_nqp_real.so'))
    fnqp.func.argtypes = (ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.c_void_p)
    fnqp.func.restype = ctypes.c_double   
    nqp = np.zeros(N)
    for m in range(N):
        Emax = 300*kb_eV*Tlist[m]
        args = ctypes.cast(arrArgs(*[params['G'], params['Delta'], Tlist[m], N0, kb_eV]), ctypes.c_void_p)
        funcC = LowLevelCallable(fnqp.func, args)
        nqp[m] = integrate.quad(funcC,Emin,Emax)[0]
    xi = (hbar_eV * np.pi * freslist)/(kb_eV * Tlist)
    k2 = 1 / (2 * N0 * params['Delta']) * (1 + np.sqrt(2 * params['Delta']/(np.pi * kb_eV * Tlist)) * np.exp(-xi) * sp.iv(0, xi))
    err = -params['alpha']/2 * k2 * nqp *params['f0'] + params['f0'] - freslist
    return err

 
def minimize_Qi_for_lmfit(params, Tlist, freslist, Qilist):
    Emin = 0
    N = np.size(Tlist)  
    arrArgs = ctypes.c_double * 5
    # fnqp = ctypes.CDLL(os.path.abspath('func_nqp_real.so'))
    fnqp = ctypes.CDLL(os.path.abspath('rfsocinterface/analysis/KID_fitting_analysis/func_nqp_real.so'))
    fnqp.func.argtypes = (ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.c_void_p)
    fnqp.func.restype = ctypes.c_double   
    nqp = np.zeros(N)
    for m in range(N):
        Emax = 300*kb_eV*Tlist[m]
        args = ctypes.cast(arrArgs(*[params['G'], params['Delta'], Tlist[m], N0, kb_eV]), ctypes.c_void_p)
        funcC = LowLevelCallable(fnqp.func, args)
        nqp[m] = integrate.quad(funcC,Emin,Emax)[0]
    xi = (hbar_eV * np.pi * freslist)/(kb_eV * Tlist)
    k1 = 1 / (np.pi * N0 * params['Delta']) * np.sqrt(2 * params['Delta']/(np.pi * kb_eV * Tlist)) * np.sinh(xi) * sp.kn(0, xi)
    err = params['alpha'] * k1 * nqp + 1/params['Qi0'] - 1/Qilist
    return err

def MB_fit(freslist, Qilist, Tlist):
    Tlist = np.array(Tlist)/1e3
    G_ini, Delta_ini = 3e-6, 2.08e-4

    print('Res %.3f MHz...'%(freslist[0]/1e6))
    par_fres = lf.Parameters()
    par_fres.add('alpha', value=0.3, min=0.1, max=1)
    par_fres.add('Delta', value=Delta_ini, min=0.5e-4, max=5e-4)
    par_fres.add('f0', value=np.max(freslist), min=np.max(freslist), max=np.max(freslist)*1.003)
    par_fres.add('G', expr='0')   
    miniFres = lf.Minimizer(minimize_f_for_lmfit, par_fres, nan_policy='omit', fcn_args=(Tlist, freslist))
    # To hide Runtime warnings that appear when calculating the stderr of alpha because it is equal to 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out1Fres = miniFres.minimize(method='BFGS')
        out2Fres = miniFres.minimize(method='Nelder', params=out1Fres.params)    

    par_qi = lf.Parameters()
    par_qi.add('alpha', value=0.3, min=0.1, max=1)
    par_qi.add('Delta', value=Delta_ini, min=0.5e-4, max=5e-4)
    par_qi.add('Qi0', value=np.max(Qilist), min=np.max(Qilist)/3, max=np.max(Qilist)*3)
    par_qi.add('G', expr='0')   
    miniQi = lf.Minimizer(minimize_Qi_for_lmfit, par_qi, nan_policy='omit', fcn_args=(Tlist, freslist, Qilist))
    # To hide Runtime warnings that appear when calculating the stderr of alpha because it is equal to 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out1Qi = miniQi.minimize(method='BFGS')
        out2Qi = miniQi.minimize(method='Nelder', params=out1Qi.params)
    return out2Fres.params, out2Qi.params